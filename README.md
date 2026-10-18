# ARUS — Smart IoT Energy Monitoring & Electrical Analytics

Aplikasi web responsif **Flask + PostgreSQL** dengan **landing page** dan **dashboard energi**. Seluruh use case dari dokumen *USE CASE EMBEDDED SYSTEM* diturunkan ke fitur prototipe: akuisisi (simulasi/REST), validasi, timestamp, penyimpanan data, grafik historis, estimasi biaya, peak analysis, forecasting sederhana, peringatan, dan rekomendasi.

> **Status saat ini:** prototipe dengan **data dummy yang benar-benar disimpan di PostgreSQL**. Simulasi bukan data sensor asli dan bukan alarm keselamatan listrik bersertifikat. Fungsi reconnect/local buffer merupakan tanggung jawab firmware IoT dan belum diterapkan di perangkat.

## Quick start — dengan Docker (paling mudah)

Memerlukan Docker Desktop/Engine + Docker Compose.

```bash
# Dari direktori arus-energy
cp .env.example .env
# Opsional: edit .env untuk mengganti SECRET_KEY dan IOT_API_KEY
# Khusus docker-compose, DATABASE_URL internal otomatis diatur di compose.
docker compose up --build -d
```

Akses:

- Landing page: **http://localhost:5000/**
- Dashboard: **http://localhost:5000/dashboard**
- Cek database: **http://localhost:5000/api/health**

Pada startup pertama, aplikasi otomatis membuat tabel dan menambahkan **2.881 pembacaan dummy** (interval 15 menit, periode 30 hari), pengaturan contoh, dan 3 peringatan ke PostgreSQL. Berkas volume database disimpan di `postgres_data` meskipun kontainer dihentikan.

```bash
docker compose logs -f web       # log server
docker compose down              # hentikan (tanpa menghapus database)
docker compose down -v           # hapus volume database (hati-hati)
```

## Menjalankan tanpa Docker

Memerlukan Python 3.10+ dan PostgreSQL berjalan di `localhost:5432`. Buat database/user yang cocok dengan `DATABASE_URL` pada `.env`.

```bash
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env            # Windows: copy .env.example .env
python index.py
```

PostgreSQL **harus menyala** untuk API; jika mati, landing page tetap bisa dibuka dan dashboard memberi pesan status koneksi yang jelas. Tabel dibuat otomatis saat aplikasi mulai.

### Menggunakan Neon

Salin connection string dari **Neon Console → Connect**, lalu simpan sebagai `DATABASE_URL` di `.env`. URL Neon standar otomatis memakai driver Psycopg 3; pertahankan parameter `sslmode=require`.

```bash
cp .env.example .env
# Edit DATABASE_URL dengan URL Neon, misalnya:
# postgresql://USER:PASSWORD@HOST.neon.tech/DBNAME?sslmode=require
python index.py
```

Saat aplikasi pertama kali tersambung, tabel dibuat otomatis. `docker compose up --build` juga memakai `DATABASE_URL` dari `.env` bila tersedia; tanpa itu Compose memakai PostgreSQL lokal.

## Tampilan dan fitur

**Landing page:** hero produk, fitur monitoring, tiga lapisan arsitektur (IoT Device → Backend → User), CTA langsung ke dashboard, tampilan responsif.

**Dashboard:**

1. Kartu metrik daya saat ini, energi 24 jam, estimasi biaya 30 hari, dan peak power.
2. Grafik rata-rata daya & energi untuk **24 jam / 7 hari / 30 hari** (SVG mandiri, tanpa library chart CDN).
3. Telemetri tegangan, arus, frekuensi, dan faktor daya.
4. Forecast konsumsi & biaya tujuh hari (baseline moving average + trend, **bukan ML**).
5. Daftar alert berdasarkan konfigurasi ambang, tombol "dibaca", dan rekomendasi analitik.
6. Riwayat pengukuran dengan unduhan CSV (data dalam rentang terpilih).
7. Pengaturan tarif listrik Rp/kWh dan ambang daya/tegangan yang tersimpan di PostgreSQL.
8. Tombol **Simulasi data baru**: menambahkan satu pembacaan demo ke database.
9. Refresh manual serta auto-refresh read-only tiap 20 detik.

**Catatan:** tarif Rp1.444,70/kWh hanyalah **nilai dummy yang dapat diubah**, bukan tarif PLN terkini. Forecast sederhana bukan model ML. Status "online" berarti pembacaan terbaru berumur kurang dari 20 menit; tidak membuktikan hardware terhubung saat demo.

## Saat IoT ESP32-S3 + PZEM-004T sudah jadi

Dashboard **tidak perlu ditulis ulang**. Firmware hanya harus mengirim JSON melalui endpoint `POST /api/ingest` dengan header `X-API-Key`.

```bash
curl -X POST http://localhost:5000/api/ingest \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: development-iot-key-change-me' \
  -d '{
    "device_id": "esp32-s3-01",
    "timestamp": "2026-10-18T14:00:00Z",
    "voltage_v": 221.8,
    "current_a": 2.15,
    "power_w": 448.3,
    "energy_kwh": 250.12345,
    "frequency_hz": 50.01,
    "power_factor": 0.94
  }'
```

Ganti contoh timestamp dengan waktu ISO UTC sekarang (`Z`) dan ganti API key melalui `.env`/`docker-compose` sebelum koneksi nyata. Timestamp bersifat opsional (akan diisi server jika kosong), tetapi kalau dikirim wajib menyertakan zona waktu. Data meter harus memakai **kWh kumulatif**, bukan kWh penggunaan interval. Tujuh field sensor adalah numerik dan wajib ada. Server menolak input di luar batas, duplikat timestamp, dan key tidak valid.

Contoh publisher Python juga tersedia: `python examples/send_iot.py` (gunakan `IOT_API_KEY` dan `ARUS_URL` dari environment).

**Urutan migrasi ke hardware:**

1. Matikan `AUTO_SEED_DEMO` dan `DEMO_MODE` di konfigurasi web untuk deployment berikutnya.
2. Bersihkan hanya **data demo** dari PostgreSQL (atau gunakan database baru); jangan campur kWh kumulatif dummy dengan nilai meter asli karena counter-nya berbeda. Contoh lewat `psql`:

   ```sql
   DELETE FROM measurements WHERE source = 'demo';
   DELETE FROM alerts WHERE source = 'demo';
   ```

3. Set API key yang kuat dan pastikan jalur HTTPS, idealnya dengan autentikasi pengguna.
4. Firmware ESP32-S3 membaca PZEM-004T, memvalidasi nilai, memberi timestamp, menaruh pembacaan ke local buffer jika offline, dan mengirim ulang saat terkoneksi. **Buffer dan sinkronisasi ini harus diimplementasikan di firmware**, bukan disimpulkan sudah ada pada prototipe web.
5. Kirim JSON sesuai skema di atas; data langsung dipakai dashboard.

**Penting:** Modifikasi rangkaian PLN/AC berisiko sengatan. Gunakan instalasi aman dengan bantuan orang kompeten, isolasi, sekring, dan penutup sesuai standar.

## API ringkas

| Method | URL | Tujuan |
|---|---|---|
| GET | `/api/health` | Kesehatan koneksi PostgreSQL |
| GET | `/api/devices` | Daftar perangkat |
| GET | `/api/overview?period=24h` | Seluruh data dashboard; periode `24h`, `7d`, `30d` |
| GET | `/api/history?limit=12` | N data terbaru, maksimal 100 |
| GET | `/api/export.csv?period=30d` | Unduh file CSV |
| GET | `/api/settings` | Baca tarif dan ambang |
| PUT | `/api/settings` | Simpan tarif dan ambang (angka) |
| POST | `/api/alerts/<id>/ack` | Tandai alert sudah dibaca |
| POST | `/api/ingest` | Terima data IoT (butuh `X-API-Key`) |
| POST | `/api/demo/tick` | Tambah satu data dummy (hanya demo mode) |
| POST | `/api/demo/reset` | Reset 30 hari data demo (hanya demo mode) |

API menggunakan `device_id=esp32-s3-01` sebagai default; endpoint data mendukung query `device_id` agar nantinya bisa menangani beberapa perangkat. Prototype belum menerapkan akun, autentikasi dashboard, pembatasan laju, per-device authorization, WebSocket/MQTT, atau inferensi model ML. Tambahkan sebelum dipakai pada jaringan publik. Di deployment non-demo, idealnya batasi akses ke endpoint pengaturan dan alert dengan login.

## Tabel PostgreSQL

- **`measurements`** — `device_id`, `timestamp` (UTC), `voltage_v`, `current_a`, `power_w`, `energy_kwh`, `frequency_hz`, `power_factor`, `source`, `received_at`. Constraint unik `(device_id, timestamp)` mencegah duplikasi.
- **`devices`** — `device_id`, `name`, `location`, `last_seen`, `source`.
- **`settings`** — `device_id` sebagai primary key, `tariff_per_kwh`, `power_limit_w`, `voltage_min_v`, `voltage_max_v`.
- **`alerts`** — `device_id`, `timestamp`, `title`, `message`, `category`, `severity`, `status`, `source`.

Energi per rentang dihitung dari **selisih pembacaan counter kumulatif** (delta kWh positif). Pada reset meter delta negatif diabaikan, bukan ditafsirkan sebagai penghematan. Untuk akurasi maksimal, normalisasi meter reset dengan baseline khusus saat integrasi hardware.

## Struktur folder

```text
arus-energy/
├── index.py                  # Entry point Vercel, Gunicorn, dan lokal
├── app/
│   ├── __init__.py            # Flask routes, PostgreSQL, validasi ingest
│   ├── database.py            # Model SQLAlchemy dan constraint database
│   ├── analytics.py           # KPI, agregasi, forecast, rekomendasi
│   ├── seed.py                # data dummy 30 hari
│   ├── templates/
│   │   ├── landing.html
│   │   └── dashboard.html
│   └── static/
│       ├── css/styles.css
│       ├── js/dashboard.js
│       └── icons.svg
├── examples/
│   ├── esp32_payload.json
│   └── send_iot.py
├── tests/
├── requirements.txt
├── docker-compose.yml
├── Dockerfile
├── requirements-dev.txt
├── docs/USE_CASE_MAPPING.md
└── .env.example
```

## Menjalankan tes

```bash
pip install -r requirements-dev.txt
pytest -q
```

Frontend self-contained kecuali webfont opsional dari Google Fonts: bila offline, font sistem tetap digunakan. Backend menggunakan satu worker di Docker untuk menghindari beberapa worker melakukan seed saat startup. Aplikasi ini layak untuk prototipe dan presentasi, tetapi memerlukan hardening sebelum dipublikasikan.
