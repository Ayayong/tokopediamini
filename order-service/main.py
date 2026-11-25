import os
import json
import time
import datetime
import threading
from collections import defaultdict, deque

import httpx
import pika
from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, ConfigDict
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker, Session

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./orders.db")
USER_SERVICE_URL = os.getenv("USER_SERVICE_URL", "http://127.0.0.1:8001")
PRODUCT_SERVICE_URL = os.getenv("PRODUCT_SERVICE_URL", "http://127.0.0.1:8002")
NOTIFICATION_SERVICE_URL = os.getenv("NOTIFICATION_SERVICE_URL", "http://127.0.0.1:8005")
RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@127.0.0.1:5672/%2F")
INTERNAL_KEY = os.getenv("INTERNAL_KEY", "kunci-internal-prototipe")

RATE_LIMIT = 5      # maksimal permintaan flash sale
RATE_WINDOW = 10    # per berapa detik, untuk tiap pengguna
MAX_QTY = 20        # maksimal jumlah barang per pesanan biasa

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    product_id = Column(Integer, nullable=False)
    product_name = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False)
    total_price = Column(Float, nullable=False)
    status = Column(String, nullable=False, default="MENUNGGU_PEMBAYARAN")
    created_at = Column(
        DateTime,
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
    )


Base.metadata.create_all(bind=engine)


class OrderIn(BaseModel):
    product_id: int
    quantity: int


class FlashOrderIn(BaseModel):
    flash_sale_id: int
    quantity: int = 1


class OrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    user_id: int
    product_id: int
    product_name: str
    quantity: int
    total_price: float
    status: str
    created_at: datetime.datetime


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


security = HTTPBearer()


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    """Tanya User Service: siapa pemilik token ini?"""
    try:
        resp = httpx.get(
            USER_SERVICE_URL + "/me",
            headers={"Authorization": "Bearer " + credentials.credentials},
            timeout=5,
        )
    except httpx.RequestError:
        raise HTTPException(status_code=503, detail="User Service tidak dapat dihubungi")
    if resp.status_code != 200:
        raise HTTPException(status_code=401, detail="Token tidak valid atau sudah kedaluwarsa")
    return resp.json()


def kirim_notifikasi(user_id: int, event_type: str, message: str):
    """Kirim event lewat RabbitMQ. Kalau RabbitMQ mati, pakai HTTP. Kalau keduanya gagal, pesanan tetap berjalan."""
    payload = {"user_id": user_id, "event_type": event_type, "message": message}
    try:
        params = pika.URLParameters(RABBITMQ_URL)
        params.connection_attempts = 1
        params.socket_timeout = 2
        params.stack_timeout = 2
        conn = pika.BlockingConnection(params)
        ch = conn.channel()
        ch.queue_declare(queue="notifications", durable=True)
        ch.basic_publish(
            exchange="",
            routing_key="notifications",
            body=json.dumps(payload),
            properties=pika.BasicProperties(delivery_mode=2),
        )
        conn.close()
        return
    except Exception:
        pass
    try:
        httpx.post(
            NOTIFICATION_SERVICE_URL + "/internal/notifications",
            headers={"X-Internal-Key": INTERNAL_KEY},
            json=payload,
            timeout=3,
        )
    except Exception:
        pass


_hits = defaultdict(deque)
_hits_lock = threading.Lock()


def check_rate_limit(user_id: int):
    now = time.time()
    with _hits_lock:
        q = _hits[user_id]
        while q and now - q[0] > RATE_WINDOW:
            q.popleft()
        if len(q) >= RATE_LIMIT:
            raise HTTPException(
                status_code=429,
                detail="Terlalu banyak permintaan, coba lagi beberapa detik lagi",
            )
        q.append(now)


app = FastAPI(title="Order Service")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/orders", response_model=OrderOut, status_code=201)
def create_order(
    data: OrderIn,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if data.quantity <= 0:
        raise HTTPException(status_code=400, detail="Jumlah harus lebih dari 0")
    if data.quantity > MAX_QTY:
        raise HTTPException(status_code=400, detail="Maksimal " + str(MAX_QTY) + " barang per pesanan")

    try:
        prod_resp = httpx.get(PRODUCT_SERVICE_URL + "/products/" + str(data.product_id), timeout=5)
    except httpx.RequestError:
        raise HTTPException(status_code=503, detail="Product Service tidak dapat dihubungi")
    if prod_resp.status_code == 404:
        raise HTTPException(status_code=404, detail="Produk tidak ditemukan")
    if prod_resp.status_code != 200:
        raise HTTPException(status_code=502, detail="Product Service mengembalikan error")
    product = prod_resp.json()

    try:
        reserve = httpx.post(
            PRODUCT_SERVICE_URL + "/products/" + str(data.product_id) + "/reserve",
            json={"quantity": data.quantity},
            timeout=5,
        )
    except httpx.RequestError:
        raise HTTPException(status_code=503, detail="Product Service tidak dapat dihubungi")
    if reserve.status_code == 409:
        raise HTTPException(status_code=400, detail="Stok tidak mencukupi")
    if reserve.status_code != 200:
        raise HTTPException(status_code=502, detail="Gagal mengurangi stok")

    order = Order(
        user_id=user["id"],
        product_id=product["id"],
        product_name=product["name"],
        quantity=data.quantity,
        total_price=product["price"] * data.quantity,
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    kirim_notifikasi(
        user["id"],
        "order.created",
        "Pesanan #" + str(order.id) + " " + order.product_name + " x" + str(order.quantity)
        + " dibuat. Silakan lakukan pembayaran.",
    )
    return order


@app.post("/flash-orders", response_model=OrderOut, status_code=201)
def create_flash_order(
    data: FlashOrderIn,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    check_rate_limit(user["id"])
    if data.quantity < 1 or data.quantity > 2:
        raise HTTPException(status_code=400, detail="Jumlah flash sale 1 sampai 2 per pesanan")

    try:
        resp = httpx.post(
            PRODUCT_SERVICE_URL + "/flash-sales/" + str(data.flash_sale_id) + "/reserve",
            json={"quantity": data.quantity},
            timeout=5,
        )
    except httpx.RequestError:
        raise HTTPException(status_code=503, detail="Product Service tidak dapat dihubungi")
    if resp.status_code in (404, 409):
        raise HTTPException(status_code=400, detail=resp.json().get("detail", "Flash sale tidak tersedia"))
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail="Gagal memproses flash sale")
    flash = resp.json()

    order = Order(
        user_id=user["id"],
        product_id=flash["product_id"],
        product_name=flash["product_name"] + " (Flash Sale)",
        quantity=data.quantity,
        total_price=flash["flash_price"] * data.quantity,
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    kirim_notifikasi(
        user["id"],
        "order.created",
        "Pesanan flash sale #" + str(order.id) + " " + order.product_name + " x" + str(order.quantity)
        + " dibuat. Silakan lakukan pembayaran.",
    )
    return order


@app.get("/orders", response_model=list[OrderOut])
def list_my_orders(user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(Order).filter(Order.user_id == user["id"]).order_by(Order.id.desc()).all()


@app.get("/orders/{order_id}", response_model=OrderOut)
def get_order(order_id: int, user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    order = db.get(Order, order_id)
    if not order or order.user_id != user["id"]:
        raise HTTPException(status_code=404, detail="Pesanan tidak ditemukan")
    return order


@app.delete("/orders/{order_id}")
def delete_order(order_id: int, user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    """Hapus satu pesanan dari riwayat. Hanya pesanan yang sudah dibayar."""
    order = db.get(Order, order_id)
    if not order or order.user_id != user["id"]:
        raise HTTPException(status_code=404, detail="Pesanan tidak ditemukan")
    if order.status != "DIBAYAR":
        raise HTTPException(
            status_code=400,
            detail="Pesanan yang belum dibayar tidak bisa dihapus. Selesaikan pembayaran dulu.",
        )
    db.delete(order)
    db.commit()
    return {"status": "ok"}


@app.delete("/orders")
def delete_paid_orders(user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    """Hapus semua riwayat pesanan yang sudah dibayar milik pengguna ini."""
    jumlah = (
        db.query(Order)
        .filter(Order.user_id == user["id"], Order.status == "DIBAYAR")
        .delete()
    )
    db.commit()
    return {"status": "ok", "dihapus": jumlah}


@app.post("/internal/orders/{order_id}/paid", response_model=OrderOut)
def mark_order_paid(
    order_id: int,
    x_internal_key: str = Header(default=""),
    db: Session = Depends(get_db),
):
    """Hanya dipanggil oleh Payment Service, dilindungi kunci internal."""
    if x_internal_key != INTERNAL_KEY:
        raise HTTPException(status_code=403, detail="Akses ditolak")
    order = db.get(Order, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Pesanan tidak ditemukan")
    if order.status != "MENUNGGU_PEMBAYARAN":
        raise HTTPException(status_code=409, detail="Pesanan sudah dibayar atau tidak bisa dibayar")
    order.status = "DIBAYAR"
    db.commit()
    db.refresh(order)
    kirim_notifikasi(
        order.user_id,
        "order.paid",
        "Pembayaran pesanan #" + str(order.id) + " berhasil. Pesananmu sedang diproses.",
    )
    return order