# Pemetaan Use Case ke Prototipe ARUS

Dokumen acuan: **USE CASE EMBEDDED SYSTEM** (Smart IoT Energy Monitoring & Electrical Analytics System).

| Aktor / fungsi dalam dokumen | Implementasi prototipe Flask + PostgreSQL |
|---|---|
| IoT Device — Read electrical measurements | Dummy generator di `app/seed.py`, nanti diganti firmware ESP32-S3 + PZEM-004T |
| IoT Device — Validate measurements | Validasi payload IoT di `app/__init__.py`; validasi *di sensor* belum dibuat |
| IoT Device — Add timestamp | Server menambahkan UTC timestamp jika tidak diberikan; firmware masih perlu membuat timestamp sendiri bila ingin mempertahankan waktu sampling saat offline |
| IoT Device — Buffer data | **Belum diimplementasikan**, memerlukan buffer persisten di firmware |
| IoT Device — Transmit data | Sudah tersedia `POST /api/ingest` berbasis REST + API key |
| IoT Device — Reconnect / synchronize | **Belum diimplementasikan** di firmware; endpoint menerima pengiriman ulang berurut timestamp dan menolak duplikat |
| Backend — Receive sensor data | Endpoint REST `/api/ingest` |
| Backend — Validate incoming data | Validasi tipe, rentang, waktu, unik `(device_id,timestamp)` |
| Backend — Store data | Tabel PostgreSQL `measurements`, `devices`, `settings`, `alerts` |
| Backend — Aggregate data | Agregasi per jam/hari di `app/analytics.py` |
| Backend — Calculate consumption | Delta kWh kumulatif antar pengukuran |
| Backend — Peak analysis | Nilai maksimum daya pada 24 jam terakhir |
| Backend — Historical comparison | KPI konsumsi 24 jam vs 24 jam sebelumnya, grafik historis 24 jam / 7 hari / 30 hari |
| Backend — Cost estimation | Konsumsi kWh × tarif yang dapat diatur pengguna |
| Backend — Anomaly detection | Deteksi **berbasis ambang** daya dan tegangan. Deteksi anomali berbasis ML belum dibuat |
| Backend — Forecasting | Moving average + tren sederhana, **belum model ML** |
| Backend — Recommendation engine | Rekomendasi berbasis aturan terkait beban malam, peak, dan proyeksi anggaran |
| Backend — Generate alerts | Notifikasi dalam aplikasi dan penyimpanan di PostgreSQL (bukan push notification) |
| User — Real-time electrical data | Nilai terbaru dari PostgreSQL (auto-refresh tiap 20 detik) |
| User — Consumption graphs | Grafik SVG interaktif tanpa layanan CDN |
| User — Historical consumption | Tabel dan grafik, serta CSV export |
| User — Compare periods | 24 jam vs 24 jam sebelumnya; rentang grafik 24h / 7d / 30d |
| User — Peak power | KPI peak power 24 jam |
| User — Estimated cost | Estimasi biaya 30 hari dan prediksi 7 hari |
| User — Consumption forecast / cost forecast | Angka 7 hari + visualisasi proyeksi harian |
| User — Receive/view alerts | Daftar alert, status sudah dibaca |
| User — View recommendations | Panel rekomendasi otomatis |

## Alur data

```text
ESP32-S3 + PZEM-004T (belum disambungkan)
          |
          | POST /api/ingest + X-API-Key
          v
Flask REST API --> validasi --> PostgreSQL (measurements, settings, alerts)
                                       |
                                       v
                               app/analytics.py
                              /       |       \
                          KPI       Grafik    Forecast + Rekomendasi
                              \       |       /
                                  Dashboard

Sebelum IoT siap:
app/seed.py --> PostgreSQL --> (alur yang sama) --> Dashboard
```

## Catatan sebelum produksi

- Seluruh halaman dan API monitoring masih tanpa autentikasi login. Tambahkan otorisasi berbasis user/device, HTTPS, rate limiting, rotasi API key, dan audit log bila dipublikasikan.
- Sistem ini **monitoring**, bukan perangkat pemutus arus, pengaman kebakaran, ataupun alat ukur bersertifikat.
- Timestamp disimpan UTC; bucket harian dan saran malam menggunakan WIB (UTC+7).
- Jika sumber beralih dari dummy ke sensor dengan counter `energy_kwh` berbeda, bersihkan histori dummy atau gunakan `device_id` terpisah agar delta konsisten.
- Pemberitahuan pada dashboard bukan jaminan real-time ketika tab ditutup. Jika perlu notifikasi proaktif, tambahkan worker/task queue dan layanan push/email.
