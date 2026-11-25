import httpx

# Langsung ke Product Service (port 8002) supaya tidak kena batas permintaan gateway
BASE = "http://127.0.0.1:8002"

produk = [
    # ---- Sepatu dan alas kaki ----
    ("Sepatu NIKE", "Sport", 1000000, 50),
    ("Sepatu Lari Ultra", "Sepatu lari ringan", 650000, 40),
    ("Sepatu Sneakers Putih", "Sneakers casual", 450000, 60),
    ("Sepatu Pantofel Kulit", "Sepatu formal pria", 520000, 30),
    ("Sepatu Futsal Pro", "Sepatu futsal", 380000, 35),
    ("Sandal Gunung", "Sandal outdoor", 220000, 45),
    ("Sandal Jepit Santai", "Sandal harian", 60000, 120),
    ("Sepatu Boots Safety", "Sepatu proyek", 340000, 25),
    # ---- Tas ----
    ("Tas Ransel", "Tas sekolah dan kuliah", 180000, 50),
    ("Tas Laptop 14 Inci", "Tas laptop antiair", 275000, 40),
    ("Tas Selempang Pria", "Tas selempang", 160000, 55),
    ("Tas Tote Kanvas", "Tas belanja kanvas", 85000, 80),
    ("Tas Pinggang Sport", "Tas pinggang olahraga", 95000, 70),
    ("Tas Travel Besar", "Tas perjalanan", 420000, 20),
    ("Dompet Kulit", "Dompet bifold", 130000, 60),
    # ---- Jaket dan sweater ----
    ("Jaket Hoodie", "Jaket hangat", 250000, 50),
    ("Jaket Bomber", "Jaket bomber", 320000, 40),
    ("Jaket Jeans", "Jaket denim", 360000, 30),
    ("Jaket Parasut", "Jaket anti angin", 280000, 45),
    ("Sweater Rajut", "Sweater hangat", 190000, 50),
    ("Jaket Varsity", "Jaket gaya kampus", 340000, 25),
    # ---- Kaos dan kemeja ----
    ("Kaos Polos", "Bahan katun", 75000, 100),
    ("Kaos Oversize", "Kaos longgar", 99000, 90),
    ("Kaos Polo", "Kaos kerah", 135000, 60),
    ("Kemeja Flanel", "Kemeja kotak-kotak", 210000, 45),
    ("Kemeja Putih Formal", "Kemeja kantor", 175000, 50),
    ("Baju Koko", "Baju koko lengan panjang", 190000, 35),
    ("Kaos Olahraga Dry-Fit", "Cepat kering", 110000, 70),
    # ---- Celana ----
    ("Celana Jeans", "Celana panjang denim", 300000, 50),
    ("Celana Chino", "Celana chino slim fit", 240000, 50),
    ("Celana Jogger", "Celana santai", 160000, 70),
    ("Celana Cargo", "Celana banyak saku", 285000, 40),
    ("Celana Pendek Santai", "Celana pendek harian", 90000, 90),
    ("Celana Training", "Celana olahraga", 145000, 60),
    ("Celana Kain Formal", "Celana kantor", 230000, 40),
    # ---- Aksesoris dan elektronik ----
    ("Topi Baseball", "Topi baseball", 90000, 80),
    ("Topi Rajut", "Topi hangat", 55000, 70),
    ("Kacamata Hitam", "Lensa anti UV", 150000, 50),
    ("Jam Tangan Digital", "Tahan air", 320000, 40),
    ("Jam Tangan Analog", "Tali kulit", 450000, 30),
    ("Ikat Pinggang Kulit", "Ikat pinggang pria", 120000, 60),
    ("Kaus Kaki Sport", "Isi 3 pasang", 45000, 150),
    ("Headphone Bluetooth", "Headphone nirkabel", 350000, 45),
    ("Earbuds Nirkabel", "Earbuds dengan case", 275000, 60),
    ("Power Bank 10000mAh", "Pengisian cepat", 199000, 70),
    ("Speaker Mini Bluetooth", "Speaker portabel", 240000, 40),
    ("Mouse Wireless", "Mouse nirkabel", 125000, 80),
    ("Keyboard Mekanik", "Keyboard mekanik RGB", 480000, 30),
    ("Botol Minum 1 Liter", "Botol stainless", 75000, 100),
    ("Payung Lipat", "Payung anti UV", 65000, 90),
]

try:
    # 1. Tambah produk yang belum ada
    ada = {p["name"] for p in httpx.get(BASE + "/products", timeout=10).json()}
    baru = 0
    for nama, desk, harga, stok in produk:
        if nama in ada:
            print(nama, "-> sudah ada, dilewati")
            continue
        r = httpx.post(
            BASE + "/products",
            json={"name": nama, "description": desk, "price": harga, "stock": stok},
            timeout=10,
        )
        if r.status_code == 201:
            baru += 1
            print(nama, "-> 201")
        else:
            print(nama, "->", r.status_code, r.text)
    print("\nProduk baru yang masuk:", baru)

    # 2. Buat flash sale untuk beberapa produk
    semua = httpx.get(BASE + "/products", timeout=10).json()
    flash = httpx.get(BASE + "/flash-sales", timeout=10).json()

    # product_id yang sudah punya flash sale aktif / akan datang
    sudah_ada = {f["product_id"] for f in flash if f["status"] in ("AKTIF", "AKAN_DATANG")}

    daftar_flash = [
        {"nama": "Sepatu NIKE", "harga": 700000, "stok": 20},
        {"nama": "Jam Tangan Analog", "harga": 450000, "stok": 10},
        {"nama": "Tas Ransel", "harga": 150000, "stok": 15},
        {"nama": "Jaket Hoodie", "harga": 200000, "stok": 25},
        {"nama": "Kaos Polos", "harga": 50000, "stok": 30},
        {"nama": "Celana Jeans", "harga": 250000, "stok": 20},
        {"nama": "Headphone Bluetooth", "harga": 300000, "stok": 10},
    ]

    for item in daftar_flash:
        pid = next((x["id"] for x in semua if x["name"] == item["nama"]), None)
        if pid is None:
            print(f"{item['nama']} -> produk tidak ditemukan")
        elif pid in sudah_ada:
            print(f"{item['nama']} -> sudah ada flash sale, dilewati")
        else:
            r = httpx.post(
                BASE + "/flash-sales",
                json={
                    "product_id": pid,
                    "flash_price": item["harga"],
                    "flash_stock": item["stok"],
                    "start_in_seconds": 0,
                    "duration_seconds": 7200,
                },
                timeout=10,
            )
            print(f"{item['nama']} ->", r.status_code, r.text if r.status_code != 201 else "")
except httpx.ConnectError:
    print("Tidak bisa terhubung ke Product Service (port 8002). Cek: docker compose ps")