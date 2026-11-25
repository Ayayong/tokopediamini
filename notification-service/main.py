import os
import json
import time
import datetime
import threading
from contextlib import asynccontextmanager

import httpx
import pika
from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, ConfigDict
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker, Session

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./notifications.db")
USER_SERVICE_URL = os.getenv("USER_SERVICE_URL", "http://127.0.0.1:8001")
INTERNAL_KEY = os.getenv("INTERNAL_KEY", "kunci-internal-prototipe")
RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@127.0.0.1:5672/%2F")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


class Notification(Base):
    __tablename__ = "notifications"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    event_type = Column(String, nullable=False)
    message = Column(String, nullable=False)
    is_read = Column(Boolean, nullable=False, default=False)
    created_at = Column(
        DateTime,
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
    )


Base.metadata.create_all(bind=engine)


class NotifIn(BaseModel):
    user_id: int
    event_type: str
    message: str


class NotifOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    user_id: int
    event_type: str
    message: str
    is_read: bool
    created_at: datetime.datetime


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def simpan_notifikasi(user_id, event_type, message):
    db = SessionLocal()
    try:
        db.add(Notification(user_id=user_id, event_type=event_type, message=message))
        db.commit()
    finally:
        db.close()


def consumer_loop():
    """Membaca antrean 'notifications' dari RabbitMQ. Kalau RabbitMQ mati, coba lagi tiap 5 detik."""
    while True:
        try:
            conn = pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL))
            ch = conn.channel()
            ch.queue_declare(queue="notifications", durable=True)

            def on_message(channel, method, props, body):
                try:
                    d = json.loads(body)
                    simpan_notifikasi(d["user_id"], d["event_type"], d["message"])
                    channel.basic_ack(delivery_tag=method.delivery_tag)
                except Exception:
                    channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

            ch.basic_consume(queue="notifications", on_message_callback=on_message)
            ch.start_consuming()
        except Exception:
            time.sleep(5)


@asynccontextmanager
async def lifespan(app):
    threading.Thread(target=consumer_loop, daemon=True).start()
    yield


security = HTTPBearer()


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
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


app = FastAPI(title="Notification Service", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/internal/notifications", response_model=NotifOut, status_code=201)
def receive_event(
    data: NotifIn,
    x_internal_key: str = Header(default=""),
    db: Session = Depends(get_db),
):
    """Jalur cadangan (HTTP) kalau RabbitMQ tidak tersedia."""
    if x_internal_key != INTERNAL_KEY:
        raise HTTPException(status_code=403, detail="Akses ditolak")
    notif = Notification(user_id=data.user_id, event_type=data.event_type, message=data.message)
    db.add(notif)
    db.commit()
    db.refresh(notif)
    return notif


@app.get("/notifications", response_model=list[NotifOut])
def list_notifications(user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    return (
        db.query(Notification)
        .filter(Notification.user_id == user["id"])
        .order_by(Notification.id.desc())
        .limit(50)
        .all()
    )


@app.post("/notifications/read-all")
def read_all(user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    db.query(Notification).filter(
        Notification.user_id == user["id"], Notification.is_read == False  # noqa: E712
    ).update({"is_read": True})
    db.commit()
    return {"status": "ok"}


@app.delete("/notifications/{notif_id}")
def delete_notification(
    notif_id: int,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    notif = db.get(Notification, notif_id)
    if not notif or notif.user_id != user["id"]:
        raise HTTPException(status_code=404, detail="Notifikasi tidak ditemukan")
    db.delete(notif)
    db.commit()
    return {"status": "ok"}


@app.delete("/notifications")
def delete_all_notifications(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    jumlah = db.query(Notification).filter(Notification.user_id == user["id"]).delete()
    db.commit()
    return {"status": "ok", "dihapus": jumlah}