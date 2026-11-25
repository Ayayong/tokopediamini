import os
import datetime
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, update
from sqlalchemy.orm import declarative_base, sessionmaker, Session

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./products.db")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    description = Column(String, default="")
    price = Column(Float, nullable=False)
    stock = Column(Integer, nullable=False, default=0)


class FlashSale(Base):
    __tablename__ = "flash_sales"
    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, nullable=False, index=True)
    flash_price = Column(Float, nullable=False)
    flash_stock = Column(Integer, nullable=False)
    start_at = Column(DateTime, nullable=False)
    end_at = Column(DateTime, nullable=False)


Base.metadata.create_all(bind=engine)


class ProductIn(BaseModel):
    name: str
    description: str = ""
    price: float
    stock: int = 0


class ProductOut(ProductIn):
    model_config = ConfigDict(from_attributes=True)
    id: int


class ReserveIn(BaseModel):
    quantity: int


class FlashIn(BaseModel):
    product_id: int
    flash_price: float
    flash_stock: int
    start_in_seconds: int = 0
    duration_seconds: int = 300


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def now_utc():
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)


app = FastAPI(title="Product Service")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------- Produk ----------------
@app.get("/products", response_model=list[ProductOut])
def list_products(db: Session = Depends(get_db)):
    return db.query(Product).all()


@app.get("/products/{product_id}", response_model=ProductOut)
def get_product(product_id: int, db: Session = Depends(get_db)):
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Produk tidak ditemukan")
    return product


@app.post("/products", response_model=ProductOut, status_code=201)
def create_product(data: ProductIn, db: Session = Depends(get_db)):
    product = Product(**data.model_dump())
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


@app.put("/products/{product_id}", response_model=ProductOut)
def update_product(product_id: int, data: ProductIn, db: Session = Depends(get_db)):
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Produk tidak ditemukan")
    for key, value in data.model_dump().items():
        setattr(product, key, value)
    db.commit()
    db.refresh(product)
    return product


@app.delete("/products/{product_id}", status_code=204)
def delete_product(product_id: int, db: Session = Depends(get_db)):
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Produk tidak ditemukan")
    db.delete(product)
    db.commit()


@app.post("/products/{product_id}/reserve", response_model=ProductOut)
def reserve_stock(product_id: int, data: ReserveIn, db: Session = Depends(get_db)):
    if data.quantity <= 0:
        raise HTTPException(status_code=400, detail="Jumlah harus lebih dari 0")
    # Pengurangan atomik: hanya berhasil jika stok masih cukup
    result = db.execute(
        update(Product)
        .where(Product.id == product_id, Product.stock >= data.quantity)
        .values(stock=Product.stock - data.quantity)
    )
    db.commit()
    product = db.get(Product, product_id)
    if result.rowcount == 0:
        if not product:
            raise HTTPException(status_code=404, detail="Produk tidak ditemukan")
        raise HTTPException(status_code=409, detail="Stok tidak mencukupi")
    db.refresh(product)
    return product


# ---------------- Flash sale ----------------
def flash_to_dict(fs, db):
    now = now_utc()
    product = db.get(Product, fs.product_id)
    if now < fs.start_at:
        status = "AKAN_DATANG"
    elif now >= fs.end_at:
        status = "BERAKHIR"
    elif fs.flash_stock <= 0:
        status = "HABIS"
    else:
        status = "AKTIF"
    return {
        "id": fs.id,
        "product_id": fs.product_id,
        "product_name": product.name if product else "",
        "normal_price": product.price if product else 0,
        "flash_price": fs.flash_price,
        "flash_stock": fs.flash_stock,
        "status": status,
        "seconds_to_start": max(0, int((fs.start_at - now).total_seconds())),
        "seconds_to_end": max(0, int((fs.end_at - now).total_seconds())),
    }


@app.post("/flash-sales", status_code=201)
def create_flash_sale(data: FlashIn, db: Session = Depends(get_db)):
    if (
        data.flash_stock <= 0
        or data.flash_price <= 0
        or data.duration_seconds <= 0
        or data.start_in_seconds < 0
    ):
        raise HTTPException(status_code=400, detail="Data flash sale tidak valid")
    # Stok flash sale dipindahkan dari stok produk (atomik)
    result = db.execute(
        update(Product)
        .where(Product.id == data.product_id, Product.stock >= data.flash_stock)
        .values(stock=Product.stock - data.flash_stock)
    )
    if result.rowcount == 0:
        db.rollback()
        if not db.get(Product, data.product_id):
            raise HTTPException(status_code=404, detail="Produk tidak ditemukan")
        raise HTTPException(status_code=409, detail="Stok produk tidak cukup untuk flash sale")
    start = now_utc() + datetime.timedelta(seconds=data.start_in_seconds)
    end = start + datetime.timedelta(seconds=data.duration_seconds)
    fs = FlashSale(
        product_id=data.product_id,
        flash_price=data.flash_price,
        flash_stock=data.flash_stock,
        start_at=start,
        end_at=end,
    )
    db.add(fs)
    db.commit()
    db.refresh(fs)
    return flash_to_dict(fs, db)


@app.get("/flash-sales")
def list_flash_sales(db: Session = Depends(get_db)):
    items = db.query(FlashSale).order_by(FlashSale.id.desc()).all()
    return [flash_to_dict(fs, db) for fs in items]


@app.get("/flash-sales/{flash_id}")
def get_flash_sale(flash_id: int, db: Session = Depends(get_db)):
    fs = db.get(FlashSale, flash_id)
    if not fs:
        raise HTTPException(status_code=404, detail="Flash sale tidak ditemukan")
    return flash_to_dict(fs, db)


@app.post("/flash-sales/{flash_id}/reserve")
def reserve_flash(flash_id: int, data: ReserveIn, db: Session = Depends(get_db)):
    if data.quantity <= 0:
        raise HTTPException(status_code=400, detail="Jumlah harus lebih dari 0")
    now = now_utc()
    # Pengurangan atomik: hanya berhasil jika sedang aktif dan stok cukup
    result = db.execute(
        update(FlashSale)
        .where(
            FlashSale.id == flash_id,
            FlashSale.flash_stock >= data.quantity,
            FlashSale.start_at <= now,
            FlashSale.end_at > now,
        )
        .values(flash_stock=FlashSale.flash_stock - data.quantity)
    )
    db.commit()
    fs = db.get(FlashSale, flash_id)
    if result.rowcount == 0:
        if not fs:
            raise HTTPException(status_code=404, detail="Flash sale tidak ditemukan")
        if now < fs.start_at:
            raise HTTPException(status_code=409, detail="Flash sale belum dimulai")
        if now >= fs.end_at:
            raise HTTPException(status_code=409, detail="Flash sale sudah berakhir")
        raise HTTPException(status_code=409, detail="Stok flash sale habis")
    return flash_to_dict(fs, db)