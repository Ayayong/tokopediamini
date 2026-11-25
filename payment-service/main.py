import os
import uuid
import datetime

import httpx
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

USER_SERVICE_URL = os.getenv("USER_SERVICE_URL", "http://127.0.0.1:8001")
ORDER_SERVICE_URL = os.getenv("ORDER_SERVICE_URL", "http://127.0.0.1:8003")
INTERNAL_KEY = os.getenv("INTERNAL_KEY", "kunci-internal-prototipe")

ALLOWED_METHODS = {"TRANSFER_BANK", "E_WALLET", "KARTU_KREDIT"}

security = HTTPBearer()


class PaymentIn(BaseModel):
    order_id: int
    method: str = "TRANSFER_BANK"
    simulate_success: bool = True  # False = simulasi pembayaran gagal (untuk uji)


def get_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    return credentials.credentials


app = FastAPI(title="Payment Service")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/payments", status_code=201)
def create_payment(data: PaymentIn, token: str = Depends(get_token)):
    if data.method not in ALLOWED_METHODS:
        raise HTTPException(status_code=400, detail=f"Metode harus salah satu dari {sorted(ALLOWED_METHODS)}")

    headers = {"Authorization": f"Bearer {token}"}

    # 1. Ambil pesanan lewat Order Service (sekaligus memeriksa token dan kepemilikan)
    try:
        order_resp = httpx.get(f"{ORDER_SERVICE_URL}/orders/{data.order_id}", headers=headers, timeout=5)
    except httpx.RequestError:
        raise HTTPException(status_code=503, detail="Order Service tidak dapat dihubungi")
    if order_resp.status_code == 401:
        raise HTTPException(status_code=401, detail="Token tidak valid atau sudah kedaluwarsa")
    if order_resp.status_code == 404:
        raise HTTPException(status_code=404, detail="Pesanan tidak ditemukan")
    if order_resp.status_code != 200:
        raise HTTPException(status_code=502, detail="Order Service mengembalikan error")
    order = order_resp.json()

    if order["status"] != "MENUNGGU_PEMBAYARAN":
        raise HTTPException(status_code=400, detail="Pesanan ini tidak menunggu pembayaran")

    # 2. Simulasi pembayaran
    if not data.simulate_success:
        raise HTTPException(status_code=402, detail="Pembayaran gagal (simulasi)")

    # 3. Beri tahu Order Service bahwa pesanan sudah dibayar
    try:
        paid_resp = httpx.post(
            f"{ORDER_SERVICE_URL}/internal/orders/{data.order_id}/paid",
            headers={"X-Internal-Key": INTERNAL_KEY},
            timeout=5,
        )
    except httpx.RequestError:
        raise HTTPException(status_code=503, detail="Order Service tidak dapat dihubungi")
    if paid_resp.status_code != 200:
        raise HTTPException(status_code=502, detail="Gagal memperbarui status pesanan")

    return {
        "payment_id": str(uuid.uuid4()),
        "order_id": order["id"],
        "amount": order["total_price"],
        "method": data.method,
        "status": "BERHASIL",
        "paid_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "order_status": paid_resp.json()["status"],
    }