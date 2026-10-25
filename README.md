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

Dokumentasi gabungan rancangan perangkat, perbandingan ESP32/ESP8266, fitur web, tech stack, dan pemetaan use case tersedia dalam format Microsoft Word di [`docs/DOKUMENTASI_ARUS.docx`](docs/DOKUMENTASI_ARUS.docx).

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

### ESP8266 dengan data dummy acak

Sketch siap-upload tersedia di [`examples/send_iot_esp8266/send_iot_esp8266.ino`](examples/send_iot_esp8266/send_iot_esp8266.ino). Sketch membuat telemetri listrik dummy yang saling konsisten, menaikkan counter energi kumulatif, lalu mengirimkannya setiap 30 detik ke API ARUS.

1. Jalankan backend dengan `docker compose up --build -d`.
2. Di Arduino IDE, install board **esp8266 by ESP8266 Community**, lalu pilih board ESP8266 yang dipakai (misalnya NodeMCU 1.0).
3. Ubah `WIFI_SSID`, `WIFI_PASSWORD`, `INGEST_URL`, dan `API_KEY` di bagian atas sketch.
4. Isi `INGEST_URL` dengan URL final HTTPS, misalnya `https://arus-energy.example.com/api/ingest`, tanpa `/` di bagian akhir. `localhost` tidak dapat digunakan karena dari ESP8266 alamat itu menunjuk ke ESP8266 sendiri.
5. Upload, buka Serial Monitor pada 115200 baud, lalu cari respons `HTTP 201`.

Setelah pembacaan pertama tersimpan, pilih `esp8266-dummy-01` melalui dropdown **Perangkat** di dashboard. Pilihan disimpan dalam URL, sehingga dashboard juga bisa langsung dibuka dengan `dashboard?device_id=esp8266-dummy-01`. Data mentah dapat diperiksa lewat `GET /api/overview?device_id=esp8266-dummy-01`. Sketch memakai HTTPS dengan `setInsecure()` untuk demo: trafik tetap terenkripsi, tetapi identitas sertifikat server tidak diverifikasi. Gunakan CA certificate dan API key yang kuat untuk produksi.

### ESP32-S3 Wokwi dengan dua potensiometer

Sketch terintegrasi tersedia di [`examples/send_iot_esp32s3_wokwi/send_iot_esp32s3_wokwi.ino`](examples/send_iot_esp32s3_wokwi/send_iot_esp32s3_wokwi.ino). Potensiometer pada GPIO 4 mensimulasikan tegangan 180–250 V dan GPIO 5 mensimulasikan arus 0–10 A. Nilai dibaca setiap detik, energi kWh diakumulasi, dan satu payload dikirim ke API setiap 30 detik.

1. Di project Wokwi ESP32-S3, hubungkan pin `SIG` kedua potensiometer ke GPIO 4 dan GPIO 5; hubungkan `VCC` ke 3V3 dan `GND` ke GND.
2. Salin sketch tersebut ke Wokwi. Wi-Fi simulator sudah memakai `Wokwi-GUEST` tanpa password.
3. Ganti `INGEST_URL` dengan URL HTTPS deployment ARUS yang publik dan ganti `API_KEY` agar sama dengan `IOT_API_KEY` backend.
4. Jalankan simulasi dan periksa Serial Monitor. Respons sukses adalah `HTTP 201`.

Sketch menggunakan `DEVICE_ID` yang sama dengan default dashboard, yaitu `esp32-s3-01`. Timestamp tidak dikirim oleh perangkat agar server mengisinya dalam UTC. `localhost` tidak bisa dipakai dari Wokwi; backend lokal harus dipublikasikan melalui URL HTTPS yang dapat dijangkau simulator.

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
├── docs/DOKUMENTASI_ARUS.docx
└── .env.example
```

## Menjalankan tes

```bash
pip install -r requirements-dev.txt
pytest -q
```

Frontend self-contained kecuali webfont opsional dari Google Fonts: bila offline, font sistem tetap digunakan. Backend menggunakan satu worker di Docker untuk menghindari beberapa worker melakukan seed saat startup. Aplikasi ini layak untuk prototipe dan presentasi, tetapi memerlukan hardening sebelum dipublikasikan.
