"""Read-only telemetry analytics shared by demo and real IoT readings."""
from collections import defaultdict
from datetime import datetime, timedelta, timezone
import statistics

from .database import Alert, Device, Measurement, Setting

WIB = timezone(timedelta(hours=7))


def to_iso(dt):
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat(timespec="seconds").replace("+00:00", "Z")


def public_measurement(m):
    return {"timestamp": to_iso(m.timestamp), "voltage_v": m.voltage_v,
            "current_a": m.current_a, "power_w": m.power_w,
            "energy_kwh": m.energy_kwh, "frequency_hz": m.frequency_hz,
            "power_factor": m.power_factor, "source": m.source or "unknown"}


def get_history(device_id, limit=12):
    result = Measurement.query.filter_by(device_id=device_id).order_by(Measurement.timestamp.desc()).limit(limit)
    return [public_measurement(m) for m in result]


def series_window(readings, period, now, tariff):
    if period == "24h":
        bounds = [now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=i)
                  for i in reversed(range(24))]
        key_fn = lambda dt: dt.replace(minute=0, second=0, microsecond=0)
        active_start = now - timedelta(hours=24)
    else:
        days = 7 if period == "7d" else 30
        end_local_day = now.replace(tzinfo=timezone.utc).astimezone(WIB).date()
        dates = [end_local_day - timedelta(days=i) for i in reversed(range(days))]
        bounds = dates
        key_fn = lambda dt: dt.replace(tzinfo=timezone.utc).astimezone(WIB).date()
        active_start = datetime.combine(dates[0], datetime.min.time(), tzinfo=WIB).astimezone(timezone.utc).replace(tzinfo=None)

    aggregated = defaultdict(lambda: {"watts": [], "kwh": 0.0})
    previous = None
    for m in readings:
        ts = m.timestamp
        if previous is not None and ts >= active_start:
            delta = m.energy_kwh - previous.energy_kwh
            # A negative delta usually means a meter reset; don't invent missing energy.
            if delta >= 0:
                aggregated[key_fn(ts)]["kwh"] += delta
        if ts >= active_start:
            aggregated[key_fn(ts)]["watts"].append(m.power_w)
        previous = m

    points = []
    for key in bounds:
        item = aggregated[key]
        kwh = item["kwh"]
        if isinstance(key, datetime):
            iso = to_iso(key)
        else:
            iso = key.isoformat()
        points.append({"at": iso, "power_w": round(statistics.mean(item["watts"]), 1)
                       if item["watts"] else 0,
                       "energy_kwh": round(kwh, 3), "cost": round(kwh * tariff)})
    return points


def consumed_between(readings, start, end):
    prior = None
    value = 0.0
    for m in readings:
        ts = m.timestamp
        if ts > end:
            break
        if prior is not None and ts >= start:
            delta = m.energy_kwh - prior.energy_kwh
            if delta >= 0:
                value += delta
        prior = m
    return round(value, 3)


def daily_energy(readings, now, days=10):
    local_today = now.replace(tzinfo=timezone.utc).astimezone(WIB).date()
    start = local_today - timedelta(days=days)
    daily = defaultdict(float)
    prev = None
    for m in readings:
        date = m.timestamp.replace(tzinfo=timezone.utc).astimezone(WIB).date()
        if date >= start and prev:
            delta = m.energy_kwh - prev.energy_kwh
            if delta >= 0:
                daily[date] += delta
        prev = m
    return {date: round(daily[date], 3) for date in (start + timedelta(days=i) for i in range(days + 1))}


def simple_forecast(readings, now, tariff):
    # Transparent moving-average + gentle slope. This is a baseline, NOT an ML model.
    local_today = now.replace(tzinfo=timezone.utc).astimezone(WIB).date()
    historical = daily_energy(readings, now, 12)
    values = [historical[local_today - timedelta(days=i)] for i in reversed(range(1, 8))]
    valid = [v for v in values if v > 0]
    if not valid:
        valid = [0.0]
    avg = statistics.mean(valid)
    left = statistics.mean(valid[:max(1, len(valid)//2)])
    right = statistics.mean(valid[-max(1, len(valid)//2):])
    slope = (right - left) / max(1, len(valid))
    forecast = []
    for i in range(1, 8):
        estimate = max(0, avg + slope * (i - 1))
        forecast.append({"date": (local_today + timedelta(days=i)).isoformat(),
                         "energy_kwh": round(estimate, 2), "cost": round(estimate * tariff)})
    return {"method": "Moving average + trend sederhana (bukan model ML)",
            "days": forecast, "total_kwh": round(sum(x["energy_kwh"] for x in forecast), 2),
            "estimated_cost": round(sum(x["cost"] for x in forecast))}


def get_dashboard_data(device_id, period="24h"):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    device = Device.query.filter_by(device_id=device_id).first()
    settings = Setting.query.filter_by(device_id=device_id).first()
    tariff = float(settings.tariff_per_kwh if settings else 1444.7)
    latest = Measurement.query.filter_by(device_id=device_id).order_by(Measurement.timestamp.desc()).first()
    readings = (Measurement.query.filter(Measurement.device_id == device_id,
                Measurement.timestamp >= now - timedelta(days=32)).order_by(Measurement.timestamp.asc()).all())
    if not latest:
        return {"device_id": device_id, "empty": True, "mode": "unknown", "device": {
            "name": device.name if device else "IoT Energy Meter",
            "location": device.location if device else "Perangkat tidak ditemukan"},
            "message": "Belum ada data. Aktifkan AUTO_SEED_DEMO atau kirim data melalui /api/ingest."}

    recent = [m for m in readings if m.timestamp >= now - timedelta(hours=24)]
    energy_24 = consumed_between(readings, now - timedelta(hours=24), now)
    prev_24 = consumed_between(readings, now - timedelta(hours=48), now - timedelta(hours=24))
    energy_30 = consumed_between(readings, now - timedelta(days=30), now)
    peak = max((m.power_w for m in recent), default=0)
    avg_power = statistics.mean([m.power_w for m in recent]) if recent else 0
    rate_change = (energy_24 - prev_24) / prev_24 * 100 if prev_24 else 0
    series = series_window(readings, period, now, tariff)
    forecast = simple_forecast(readings, now, tariff)
    events = Alert.query.filter_by(device_id=device_id).order_by(Alert.timestamp.desc()).limit(7).all()
    alerts = [{"id": str(a.id), "title": a.title, "message": a.message,
               "severity": a.severity, "status": a.status or "new",
               "timestamp": to_iso(a.timestamp)} for a in events]

    local_hour = now.replace(tzinfo=timezone.utc).astimezone(WIB).hour
    night_readings = [m.power_w for m in readings[-96 * 7:]
                      if m.timestamp.replace(tzinfo=timezone.utc).astimezone(WIB).hour in (0, 1, 2, 3, 4)]
    night_avg = statistics.mean(night_readings) if night_readings else 0
    recommendations = []
    if night_avg > 200:
        recommendations.append({"title": "Kurangi beban saat malam", "description":
                                f"Rata-rata daya pukul 00.00–04.59 WIB sekitar {night_avg:.0f} W. Periksa perangkat standby.", "type": "tip"})
    else:
        recommendations.append({"title": "Pantau perangkat standby", "description":
                                "Periksa perangkat yang tetap menyala ketika tidak digunakan.", "type": "tip"})
    if peak > (settings.power_limit_w if settings else 1600):
        recommendations.append({"title": "Atur penggunaan daya tinggi", "description":
                                "Ada lonjakan melewati ambang yang ditetapkan. Hindari menyalakan beban besar bersamaan.", "type": "warning"})
    else:
        recommendations.append({"title": "Distribusi beban terkendali", "description":
                                "Puncak daya 24 jam terakhir masih di bawah ambang konfigurasi.", "type": "good"})
    recommendations.append({"title": "Rencanakan anggaran energi", "description":
                            f"Perkiraan biaya 7 hari berikutnya Rp {forecast['estimated_cost']:,.0f} berdasarkan tren historis.", "type": "info"})

    last_seen = (device.last_seen if device else None) or latest.timestamp
    freshness_s = (now - latest.timestamp).total_seconds()
    return {
        "empty": False, "device_id": device_id, "mode": latest.source or "unknown",
        "generated_at": to_iso(now), "online": 0 <= freshness_s < 20 * 60,
        "device": {"name": device.name if device else "IoT Energy Meter",
                   "location": device.location if device else "-",
                   "last_seen": to_iso(last_seen)},
        "latest": public_measurement(latest),
        "stats": {"power_w": round(latest.power_w, 1), "voltage_v": round(latest.voltage_v, 2),
                  "current_a": round(latest.current_a, 3), "power_factor": latest.power_factor,
                  "frequency_hz": latest.frequency_hz, "energy_24h_kwh": energy_24,
                  "previous_24h_kwh": prev_24, "change_24h_percent": round(rate_change, 1),
                  "energy_30d_kwh": energy_30, "cost_30d": round(energy_30 * tariff),
                  "cost_24h": round(energy_24 * tariff), "peak_24h_w": round(peak, 1),
                  "average_24h_w": round(avg_power, 1)},
        "period": period, "series": series, "forecast": forecast,
        "alerts": alerts, "unread_alerts": sum(a["status"] == "new" for a in alerts),
        "recommendations": recommendations,
        "history": get_history(device_id, 10),
        "settings": {"tariff_per_kwh": tariff,
                     "power_limit_w": settings.power_limit_w if settings else 1600},
        "sample_count": Measurement.query.filter_by(device_id=device_id).count(),
    }
