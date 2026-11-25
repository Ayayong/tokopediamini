import { useState, useEffect } from "react";
import "./App.css";

const GATEWAY = "http://127.0.0.1:8000/api";
const USER = GATEWAY + "/user";
const PRODUCT = GATEWAY + "/product";
const ORDER = GATEWAY + "/order";
const PAYMENT = GATEWAY + "/payment";
const NOTIF = GATEWAY + "/notification";

async function api(url, options) {
  const opt = options || {};
  const headers = { "Content-Type": "application/json" };
  if (opt.token) {
    headers["Authorization"] = "Bearer " + opt.token;
  }
  const res = await fetch(url, {
    method: opt.method || "GET",
    headers: headers,
    body: opt.body ? JSON.stringify(opt.body) : undefined,
  });
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    const pesan =
      data && typeof data.detail === "string"
        ? data.detail
        : "Error " + res.status;
    const err = new Error(pesan);
    err.status = res.status;
    throw err;
  }
  return data;
}

const rupiah = (n) => "Rp " + Number(n).toLocaleString("id-ID");
const dua = (n) => (n < 10 ? "0" + n : "" + n);
function format(detik) {
  const j = Math.floor(detik / 3600);
  const m = Math.floor((detik % 3600) / 60);
  const d = detik % 60;
  return dua(j) + ":" + dua(m) + ":" + dua(d);
}
function jam(iso) {
  const t = new Date(iso.endsWith("Z") ? iso : iso + "Z");
  return t.toLocaleString("id-ID");
}

// "Sepatu NIKE" -> "sepatu-nike"
function slug(nama) {
  return nama
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

// Gambar produk dari folder public/produk. Kalau tidak ada, tampil huruf berwarna.
function Gambar(props) {
  const exts = ["jpg", "png", "webp"];
  const [i, setI] = useState(0);
  const nama = props.nama;
  if (i >= exts.length) {
    return (
      <div className={"thumb c" + (props.warna % 5)}>
        {nama.charAt(0).toUpperCase()}
        {props.children}
      </div>
    );
  }
  return (
    <div className="thumb foto">
      <img
        src={"/produk/" + slug(nama) + "." + exts[i]}
        alt={nama}
        onError={() => setI(i + 1)}
      />
      {props.children}
    </div>
  );
}

// Pemilih jumlah: tombol - dan + serta kolom angka
function Stepper(props) {
  const v = props.value;
  const max = props.max;
  return (
    <div className="stepper">
      <button
        type="button"
        className="step-btn"
        disabled={v <= 1}
        onClick={() => props.onChange(v - 1)}
      >
        -
      </button>
      <input
        className="step-input"
        type="number"
        min="1"
        max={max}
        value={v}
        onChange={(e) => {
          let n = parseInt(e.target.value, 10);
          if (isNaN(n)) n = 1;
          props.onChange(Math.max(1, Math.min(max, n)));
        }}
      />
      <button
        type="button"
        className="step-btn"
        disabled={v >= max}
        onClick={() => props.onChange(v + 1)}
      >
        +
      </button>
    </div>
  );
}

export default function App() {
  const [token, setToken] = useState(localStorage.getItem("token") || "");
  const [mode, setMode] = useState("login");
  const [form, setForm] = useState({ name: "", email: "", password: "" });
  const [me, setMe] = useState(null);
  const [page, setPage] = useState("home");
  const [products, setProducts] = useState([]);
  const [orders, setOrders] = useState([]);
  const [flash, setFlash] = useState([]);
  const [notifs, setNotifs] = useState([]);
  const [fetchedAt, setFetchedAt] = useState(Date.now());
  const [nowMs, setNowMs] = useState(Date.now());
  const [msg, setMsg] = useState("");

  const [cari, setCari] = useState("");
  const [urut, setUrut] = useState("terbaru");
  const [qty, setQty] = useState({});
  const [cariOrder, setCariOrder] = useState("");
  const [statusOrder, setStatusOrder] = useState("semua");

  function getQty(key, max) {
    const v = qty[key] || 1;
    return Math.max(1, Math.min(v, Math.max(1, max)));
  }
  function ubahQty(key, nilai) {
    setQty({ ...qty, [key]: nilai });
  }

  function logout() {
    localStorage.removeItem("token");
    setToken("");
    setMe(null);
    setOrders([]);
    setNotifs([]);
    setPage("home");
    setCari("");
    setQty({});
  }

  async function loadFlash() {
    try {
      const f = await api(PRODUCT + "/flash-sales");
      setFlash(f);
      setFetchedAt(Date.now());
    } catch (e) {
      // dicoba lagi 5 detik berikutnya
    }
  }

  async function loadProducts() {
    try {
      setProducts(await api(PRODUCT + "/products"));
    } catch (e) {
      // dicoba lagi 5 detik berikutnya
    }
  }

  async function loadNotifs(tkn) {
    try {
      setNotifs(await api(NOTIF + "/notifications", { token: tkn || token }));
    } catch (e) {
      // Notification Service boleh mati tanpa mengganggu halaman lain
    }
  }

  async function loadData() {
    try {
      setProducts(await api(PRODUCT + "/products"));
      if (token) {
        setMe(await api(USER + "/me", { token: token }));
        setOrders(await api(ORDER + "/orders", { token: token }));
        loadNotifs(token);
      }
      loadFlash();
    } catch (e) {
      if (e.status === 401) {
        logout();
        setMsg("Sesi berakhir, silakan login lagi.");
      } else {
        setMsg(e.message);
      }
    }
  }

  useEffect(() => {
    if (token) {
      loadData();
    }
  }, [token]);

  useEffect(() => {
    const t = setInterval(() => setNowMs(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    if (!token) return;
    const t = setInterval(() => {
      loadFlash();
      loadProducts();
    }, 5000);
    return () => clearInterval(t);
  }, [token]);

  useEffect(() => {
    if (!token) return;
    const t = setInterval(() => loadNotifs(token), 8000);
    return () => clearInterval(t);
  }, [token]);

  // pesan melayang hilang sendiri setelah 4 detik (hanya setelah login)
  useEffect(() => {
    if (!msg || !token) return;
    const t = setTimeout(() => setMsg(""), 4000);
    return () => clearTimeout(t);
  }, [msg, token]);

  function sisa(detik) {
    const lewat = Math.floor((nowMs - fetchedAt) / 1000);
    return Math.max(0, detik - lewat);
  }

  async function bukaNotif() {
    setPage("notif");
    try {
      await api(NOTIF + "/notifications/read-all", { method: "POST", token: token });
      loadNotifs(token);
    } catch (e) {
      // abaikan
    }
  }

  async function submitAuth(e) {
    e.preventDefault();
    setMsg("");
    try {
      if (mode === "register") {
        await api(USER + "/register", { method: "POST", body: form });
        setMsg("Registrasi berhasil, silakan masuk.");
        setMode("login");
      } else {
        const d = await api(USER + "/login", {
          method: "POST",
          body: { email: form.email, password: form.password },
        });
        localStorage.setItem("token", d.access_token);
        setMsg("");
        setToken(d.access_token);
      }
    } catch (err) {
      setMsg(err.message);
    }
  }

  async function buy(p, jumlah) {
    try {
      await api(ORDER + "/orders", {
        method: "POST",
        token: token,
        body: { product_id: p.id, quantity: jumlah },
      });
      setMsg("Pesanan " + p.name + " x" + jumlah + " dibuat. Silakan bayar di menu Pesanan Saya.");
      ubahQty("p" + p.id, 1);
      loadData();
    } catch (err) {
      setMsg(err.message);
    }
  }

  async function buyFlash(f, jumlah) {
    try {
      await api(ORDER + "/flash-orders", {
        method: "POST",
        token: token,
        body: { flash_sale_id: f.id, quantity: jumlah },
      });
      setMsg("Flash sale berhasil! Pesanan " + f.product_name + " x" + jumlah + " dibuat. Silakan bayar di menu Pesanan Saya.");
      ubahQty("f" + f.id, 1);
      loadData();
    } catch (err) {
      setMsg(err.message);
      loadFlash();
    }
  }

  async function pay(o) {
    try {
      await api(PAYMENT + "/payments", {
        method: "POST",
        token: token,
        body: { order_id: o.id, method: "E_WALLET", simulate_success: true },
      });
      setMsg("Pesanan #" + o.id + " berhasil dibayar.");
      loadData();
    } catch (err) {
      setMsg(err.message);
    }
  }

  async function hapusOrder(o) {
    if (!window.confirm("Hapus pesanan #" + o.id + " dari riwayat?")) return;
    try {
      await api(ORDER + "/orders/" + o.id, { method: "DELETE", token: token });
      setMsg("Pesanan #" + o.id + " dihapus dari riwayat.");
      loadData();
    } catch (err) {
      setMsg(err.message);
    }
  }

  async function hapusSemuaOrder() {
    if (!window.confirm("Hapus semua riwayat pesanan yang sudah dibayar?")) return;
    try {
      const d = await api(ORDER + "/orders", { method: "DELETE", token: token });
      setMsg(d.dihapus + " pesanan dihapus dari riwayat.");
      loadData();
    } catch (err) {
      setMsg(err.message);
    }
  }

  async function hapusNotif(n) {
    try {
      await api(NOTIF + "/notifications/" + n.id, { method: "DELETE", token: token });
      loadNotifs(token);
    } catch (err) {
      setMsg(err.message);
    }
  }

  async function hapusSemuaNotif() {
    if (!window.confirm("Hapus semua notifikasi?")) return;
    try {
      await api(NOTIF + "/notifications", { method: "DELETE", token: token });
      setMsg("Semua notifikasi dihapus.");
      loadNotifs(token);
    } catch (err) {
      setMsg(err.message);
    }
  }

  /* ================= HALAMAN LOGIN ================= */
  if (!token) {
    return (
      <div className="login-page">
        <div className="login-box">
          <h1 className="logo center">
            tokopedia <span>mini</span>
          </h1>
          <h3 className="login-title">
            {mode === "login" ? "Masuk ke akun" : "Buat akun baru"}
          </h3>
          <p className="muted login-sub">
            {mode === "login"
              ? "Silakan masuk untuk mulai berbelanja."
              : "Isi data berikut untuk mendaftar."}
          </p>

          {msg && <div className="msg">{msg}</div>}

          <form onSubmit={submitAuth}>
            {mode === "register" && (
              <input
                placeholder="Nama lengkap"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
              />
            )}
            <input
              placeholder="Email"
              value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
            />
            <input
              type="password"
              placeholder="Password"
              value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
            />
            <button className="full" type="submit">
              {mode === "login" ? "Masuk" : "Daftar"}
            </button>
          </form>

          <p className="muted center login-switch">
            {mode === "login" ? "Belum punya akun? " : "Sudah punya akun? "}
            <button
              className="link"
              onClick={() => {
                setMsg("");
                setMode(mode === "login" ? "register" : "login");
              }}
            >
              {mode === "login" ? "Daftar sekarang" : "Masuk"}
            </button>
          </p>
        </div>
      </div>
    );
  }

  /* ================= DATA TAMPILAN ================= */
  const q = cari.trim().toLowerCase();
  const cocok = (nama, desk) =>
    nama.toLowerCase().includes(q) || (desk || "").toLowerCase().includes(q);

  let daftar = products.filter((p) => cocok(p.name, p.description));
  if (urut === "murah") {
    daftar = [...daftar].sort((a, b) => a.price - b.price);
  } else if (urut === "mahal") {
    daftar = [...daftar].sort((a, b) => b.price - a.price);
  } else if (urut === "nama") {
    daftar = [...daftar].sort((a, b) => a.name.localeCompare(b.name));
  } else {
    daftar = [...daftar].sort((a, b) => b.id - a.id);
  }

  const flashTampil = flash.filter(
    (f) => f.status !== "BERAKHIR" && cocok(f.product_name, "")
  );
  const belumDibaca = notifs.filter((n) => !n.is_read).length;

  const qo = cariOrder.trim().toLowerCase();
  const daftarOrder = orders.filter(
    (o) =>
      (statusOrder === "semua" || o.status === statusOrder) &&
      o.product_name.toLowerCase().includes(qo)
  );
  const jumlahDibayar = orders.filter((o) => o.status === "DIBAYAR").length;

  /* ================= BERANDA (SETELAH LOGIN) ================= */
  return (
    <div>
      {msg && (
        <div className="toast">
          <span>{msg}</span>
          <button className="toast-x" onClick={() => setMsg("")}>
            x
          </button>
        </div>
      )}

      <div className="bar">
        <div className="bar-in">
          <h1 className="logo">
            tokopedia <span>mini</span>
          </h1>
          <div className="nav">
            <button
              className={page === "home" ? "tab aktif" : "tab"}
              onClick={() => {
                setPage("home");
                loadProducts();
              }}
            >
              Beranda
            </button>
            <button
              className={page === "orders" ? "tab aktif" : "tab"}
              onClick={() => setPage("orders")}
            >
              Pesanan Saya
            </button>
            <button
              className={page === "notif" ? "tab aktif" : "tab"}
              onClick={bukaNotif}
            >
              Notifikasi
              {belumDibaca > 0 && <span className="badge-notif">{belumDibaca}</span>}
            </button>
          </div>
          <div className="user-box">
            <span className="halo">Halo, {me ? me.name : "..."}</span>
            <button className="out" onClick={logout}>
              Keluar
            </button>
          </div>
        </div>
      </div>

      {page === "home" && (
        <div className="hero">
          <div className="hero-in">
            <h2>Belanja mudah, stok aman</h2>
            <p>Marketplace berarsitektur microservices dengan flash sale.</p>
          </div>
        </div>
      )}

      <div className="wrap">
        {page === "home" && (
          <>
            <div className="toolbar">
              <input
                className="search"
                placeholder="Cari produk..."
                value={cari}
                onChange={(e) => setCari(e.target.value)}
              />
              <select
                className="select"
                value={urut}
                onChange={(e) => setUrut(e.target.value)}
              >
                <option value="terbaru">Terbaru</option>
                <option value="murah">Harga termurah</option>
                <option value="mahal">Harga termahal</option>
                <option value="nama">Nama A-Z</option>
              </select>
              {cari && (
                <button className="ghost" onClick={() => setCari("")}>
                  Hapus pencarian
                </button>
              )}
            </div>
            {cari && (
              <p className="muted hasil-info">
                {daftar.length + flashTampil.length} hasil untuk "{cari}"
              </p>
            )}

            {flashTampil.length > 0 && (
              <>
                <div className="judul">Flash Sale</div>
                <div className="grid">
                  {flashTampil.map((f) => {
                    const aktif = f.status === "AKTIF" && sisa(f.seconds_to_end) > 0;
                    const mulai = f.status === "AKAN_DATANG";
                    const bisaBeli = aktif && f.flash_stock > 0;
                    const maxF = Math.min(2, f.flash_stock);
                    const jmlF = getQty("f" + f.id, maxF);
                    return (
                      <div className="product flash" key={f.id}>
                        <Gambar nama={f.product_name} warna={f.product_id}>
                          <span className="badge-flash">FLASH SALE</span>
                        </Gambar>
                        <div className="info">
                          <div className="nama">{f.product_name}</div>
                          <div className="countdown">
                            {mulai
                              ? "Mulai dalam " + format(sisa(f.seconds_to_start))
                              : aktif
                              ? "Berakhir dalam " + format(sisa(f.seconds_to_end))
                              : "Flash sale selesai"}
                          </div>
                          <div className="harga merah">{rupiah(f.flash_price)}</div>
                          <div className="coret">{rupiah(f.normal_price)}</div>
                          <div className={f.flash_stock <= 3 ? "stok sedikit" : "stok"}>
                            {f.flash_stock <= 0
                              ? "Stok flash sale habis"
                              : "Sisa " + f.flash_stock + " lagi (maks. 2 per pesanan)"}
                          </div>
                          {bisaBeli && (
                            <>
                              <Stepper
                                value={jmlF}
                                max={maxF}
                                onChange={(n) => ubahQty("f" + f.id, n)}
                              />
                              <div className="subtotal">
                                Subtotal: {rupiah(f.flash_price * jmlF)}
                              </div>
                            </>
                          )}
                          <button
                            disabled={!bisaBeli}
                            onClick={() => buyFlash(f, jmlF)}
                          >
                            {mulai
                              ? "Belum dimulai"
                              : f.flash_stock <= 0
                              ? "Habis"
                              : aktif
                              ? "Beli Flash " + jmlF
                              : "Berakhir"}
                          </button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </>
            )}

            <div className="judul">Produk</div>
            {products.length === 0 && <p className="muted">Belum ada produk.</p>}
            {products.length > 0 && daftar.length === 0 && (
              <p className="muted">Tidak ada produk yang cocok dengan pencarianmu.</p>
            )}
            <div className="grid">
              {daftar.map((p) => {
                const maxQ = Math.min(20, p.stock);
                const jml = getQty("p" + p.id, maxQ);
                return (
                  <div className="product" key={p.id}>
                    <Gambar nama={p.name} warna={p.id} />
                    <div className="info">
                      <div className="nama">{p.name}</div>
                      <div className="desc">{p.description}</div>
                      <div className="harga">{rupiah(p.price)}</div>
                      <div className={p.stock <= 5 ? "stok sedikit" : "stok"}>
                        {p.stock <= 0
                          ? "Stok habis"
                          : p.stock <= 5
                          ? "Sisa " + p.stock + " lagi!"
                          : "Stok: " + p.stock}
                      </div>
                      {p.stock > 0 && (
                        <>
                          <Stepper
                            value={jml}
                            max={maxQ}
                            onChange={(n) => ubahQty("p" + p.id, n)}
                          />
                          <div className="subtotal">Subtotal: {rupiah(p.price * jml)}</div>
                        </>
                      )}
                      <button disabled={p.stock <= 0} onClick={() => buy(p, jml)}>
                        {p.stock <= 0 ? "Habis" : "Beli " + jml}
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          </>
        )}

        {page === "orders" && (
          <>
            <div className="judul">Pesanan Saya</div>
            <div className="toolbar">
              <input
                className="search"
                placeholder="Cari pesanan..."
                value={cariOrder}
                onChange={(e) => setCariOrder(e.target.value)}
              />
              <select
                className="select"
                value={statusOrder}
                onChange={(e) => setStatusOrder(e.target.value)}
              >
                <option value="semua">Semua status</option>
                <option value="MENUNGGU_PEMBAYARAN">Menunggu pembayaran</option>
                <option value="DIBAYAR">Sudah dibayar</option>
              </select>
              {jumlahDibayar > 0 && (
                <button className="hapus" onClick={hapusSemuaOrder}>
                  Hapus semua yang sudah dibayar ({jumlahDibayar})
                </button>
              )}
            </div>
            {orders.length === 0 && <p className="muted">Belum ada pesanan.</p>}
            {orders.length > 0 && daftarOrder.length === 0 && (
              <p className="muted">Tidak ada pesanan yang cocok.</p>
            )}
            {daftarOrder.map((o) => (
              <div className="card row order" key={o.id}>
                <div>
                  <div className="nama">
                    #{o.id} {o.product_name} × {o.quantity}
                  </div>
                  <div className="harga">{rupiah(o.total_price)}</div>
                  <span className={o.status === "DIBAYAR" ? "tag paid" : "tag"}>
                    {o.status === "DIBAYAR" ? "Sudah dibayar" : "Menunggu pembayaran"}
                  </span>
                </div>
                <div className="aksi">
                  {o.status === "MENUNGGU_PEMBAYARAN" && (
                    <button onClick={() => pay(o)}>Bayar</button>
                  )}
                  {o.status === "DIBAYAR" && (
                    <button className="hapus" onClick={() => hapusOrder(o)}>
                      Hapus
                    </button>
                  )}
                </div>
              </div>
            ))}
          </>
        )}

        {page === "notif" && (
          <>
            <div className="judul">Notifikasi</div>
            {notifs.length > 0 && (
              <div className="toolbar">
                <button className="hapus" onClick={hapusSemuaNotif}>
                  Hapus semua notifikasi
                </button>
              </div>
            )}
            {notifs.length === 0 && <p className="muted">Belum ada notifikasi.</p>}
            {notifs.map((n) => (
              <div
                className={n.is_read ? "card row notif" : "card row notif baru"}
                key={n.id}
              >
                <div>
                  <div className="notif-pesan">{n.message}</div>
                  <div className="muted">{jam(n.created_at)}</div>
                </div>
                <button className="hapus kecil" onClick={() => hapusNotif(n)}>
                  Hapus
                </button>
              </div>
            ))}
          </>
        )}
      </div>
    </div>
  );
}