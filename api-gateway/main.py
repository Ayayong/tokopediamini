import os
import time
import threading
from collections import defaultdict, deque

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

SERVICES = {
    "user": os.getenv("USER_URL", "http://127.0.0.1:8001"),
    "product": os.getenv("PRODUCT_URL", "http://127.0.0.1:8002"),
    "order": os.getenv("ORDER_URL", "http://127.0.0.1:8003"),
    "payment": os.getenv("PAYMENT_URL", "http://127.0.0.1:8004"),
    "notification": os.getenv("NOTIFICATION_URL", "http://127.0.0.1:8005"),
}

GW_LIMIT = 120   # maksimal permintaan per alamat IP
GW_WINDOW = 60   # per berapa detik
_hits = defaultdict(deque)
_lock = threading.Lock()

app = FastAPI(title="API Gateway")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def limited(ip: str) -> bool:
    now = time.time()
    with _lock:
        q = _hits[ip]
        while q and now - q[0] > GW_WINDOW:
            q.popleft()
        if len(q) >= GW_LIMIT:
            return True
        q.append(now)
        return False


@app.get("/")
def root():
    return {"service": "API Gateway", "routes": ["/api/" + n + "/..." for n in SERVICES]}


@app.get("/health")
async def health():
    hasil = {}
    async with httpx.AsyncClient(timeout=2) as client:
        for nama, base in SERVICES.items():
            try:
                r = await client.get(base + "/openapi.json")
                hasil[nama] = "UP" if r.status_code == 200 else "ERROR"
            except httpx.RequestError:
                hasil[nama] = "DOWN"
    return hasil


@app.api_route("/api/{service}/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy(service: str, path: str, request: Request):
    base = SERVICES.get(service)
    if not base:
        return JSONResponse(status_code=404, content={"detail": "Layanan tidak dikenal"})
    # Jalur internal antarlayanan tidak boleh dibuka lewat gateway
    if path.startswith("internal"):
        return JSONResponse(status_code=403, content={"detail": "Akses ditolak"})
    ip = request.client.host if request.client else "unknown"
    if limited(ip):
        return JSONResponse(status_code=429, content={"detail": "Terlalu banyak permintaan ke gateway"})

    headers = {}
    for k in ("authorization", "content-type"):
        if k in request.headers:
            headers[k] = request.headers[k]
    body = await request.body()
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.request(
                request.method,
                base + "/" + path,
                params=request.query_params,
                content=body,
                headers=headers,
            )
    except httpx.RequestError:
        return JSONResponse(status_code=503, content={"detail": "Layanan " + service + " tidak dapat dihubungi"})
    return Response(
        content=resp.content,
        status_code=resp.status_code,
        media_type=resp.headers.get("content-type"),
    )