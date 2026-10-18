"""Deterministic dummy telemetry so the prototype is usable before hardware exists."""
from datetime import datetime, timedelta, timezone
import math
import random

from .database import Alert, Device, Measurement, Setting, db


def seed_database(device_id="esp32-s3-01", reset=False):
    if not reset and db.session.query(Measurement.id).filter_by(device_id=device_id).first():
        return 0
    if reset:
        db.session.query(Measurement).filter_by(device_id=device_id, source="demo").delete()
        db.session.query(Alert).filter_by(device_id=device_id, source="demo").delete()

    now = datetime.now(timezone.utc).replace(tzinfo=None, second=0, microsecond=0)
    rng = random.Random(20261018)
    start = now - timedelta(days=30)
    total_kwh = 125.0
    records = []
    previous_power = 400
    for i in range(30 * 24 * 4 + 1):
        timestamp = start + timedelta(minutes=15 * i)
        hour = timestamp.hour + timestamp.minute / 60
        workday = timestamp.weekday() < 5
        base = 155 + 105 * math.sin(i / 29) ** 2
        if 6 <= hour < 9:
            base += 310
        elif 9 <= hour < 17:
            base += 410 if workday else 220
        elif 17 <= hour < 23:
            base += 720
        if not workday:
            base += 70
        power = max(70, min(2300, base + rng.gauss(0, 92)))
        if i % 457 == 0 and i > 0:
            power = 1820 + rng.random() * 220
        voltage = max(196, min(242, 222.6 + rng.gauss(0, 2.5)))
        factor = round(max(.78, min(.99, .93 + rng.gauss(0, .018))), 3)
        if i:
            total_kwh += (power + previous_power) / 2 / 1000 * .25
        previous_power = power
        records.append(Measurement(device_id=device_id, timestamp=timestamp,
                        voltage_v=round(voltage, 2), current_a=round(power / (voltage * factor), 3),
                        power_w=round(power, 2), energy_kwh=round(total_kwh, 5),
                        frequency_hz=round(50 + rng.gauss(0, .045), 2),
                        power_factor=factor, source="demo", received_at=now))
    db.session.add_all(records)
    device = db.session.get(Device, device_id)
    if device is None:
        device = Device(device_id=device_id, name="Smart Plug Utama", location="Ruang Utama")
        db.session.add(device)
    device.last_seen = now
    device.source = "demo"
    if db.session.get(Setting, device_id) is None:
        db.session.add(Setting(device_id=device_id))
    for d_ago, title, message, category, severity in [
        (0.9, "Lonjakan daya terdeteksi", "Daya melebihi pola konsumsi biasanya.", "high_power", "warning"),
        (3.2, "Tegangan perlu diperhatikan", "Nilai tegangan sempat mendekati batas konfigurasi.", "low_voltage", "warning"),
        (6.1, "Ringkasan konsumsi siap", "Laporan penggunaan mingguan tersedia.", "daily_summary", "info"),
    ]:
        db.session.add(Alert(device_id=device_id, timestamp=now - timedelta(days=d_ago),
                             title=title, message=message, category=category,
                             severity=severity, status="new", source="demo"))
    db.session.commit()
    return len(records)
