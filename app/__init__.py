"""ARUS — Smart IoT Energy Monitoring & Electrical Analytics System."""
import logging
import os
from datetime import datetime, timezone
from functools import wraps
from hmac import compare_digest

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request, current_app, Response
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from .analytics import get_dashboard_data, get_history, to_iso
from .database import Alert, Device, Measurement, Setting, db
from .seed import seed_database

load_dotenv()
log = logging.getLogger(__name__)


def is_true(value):
    return str(value).lower().strip() in ("1", "true", "yes", "on")


def sqlalchemy_database_url(raw_url):
    """Use psycopg 3 for provider URLs such as Neon's postgresql:// string."""
    if raw_url.startswith("postgres://"):
        return "postgresql+psycopg://" + raw_url.removeprefix("postgres://")
    if raw_url.startswith("postgresql://"):
        return "postgresql+psycopg://" + raw_url.removeprefix("postgresql://")
    return raw_url


def get_db():
    return db


def json_error(message, status=400):
    return jsonify({"error": message}), status


def now_utc():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def validate_device_id(raw):
    if not isinstance(raw, str) or not raw or len(raw) > 64:
        raise ValueError("device_id harus berupa string (1–64 karakter).")
    if not all(c.isalnum() or c in "_-" for c in raw):
        raise ValueError("device_id hanya boleh huruf, angka, '-' dan '_'.")
    return raw


def current_device():
    return validate_device_id(request.args.get("device_id") or current_app.config["DEFAULT_DEVICE_ID"])


def parse_timestamp(raw):
    if not raw:
        return now_utc()
    if not isinstance(raw, str):
        raise ValueError("timestamp harus ISO 8601, mis. 2026-10-18T10:00:00Z.")
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("timestamp harus format ISO 8601.") from exc
    if dt.tzinfo is None:
        raise ValueError("timestamp harus memiliki zona waktu (mis. Z atau +07:00).")
    result = dt.astimezone(timezone.utc).replace(tzinfo=None)
    if result > now_utc():
        raise ValueError("timestamp tidak boleh berada di masa depan.")
    return result


def require_iot_key(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        key = current_app.config.get("IOT_API_KEY", "")
        supplied = request.headers.get("X-API-Key", "")
        if not key or not compare_digest(key, supplied):
            return json_error("X-API-Key tidak valid.", 401)
        return fn(*args, **kwargs)
    return wrapper


def validate_measurement(payload):
    if not isinstance(payload, dict):
        raise ValueError("Body harus berupa JSON object.")
    device_id = validate_device_id(payload.get("device_id", ""))
    allowed = {
        "voltage_v": (0, 300), "current_a": (0, 100),
        "power_w": (0, 25000), "energy_kwh": (0, 10000000),
        "frequency_hz": (0, 80), "power_factor": (0, 1),
    }
    values = {}
    for field, (low, high) in allowed.items():
        value = payload.get(field)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{field} harus angka ({low}–{high}).")
        import math
        if not math.isfinite(value) or not low <= value <= high:
            raise ValueError(f"{field} di luar rentang {low}–{high}.")
        values[field] = round(float(value), 5)
    return {"device_id": device_id, "timestamp": parse_timestamp(payload.get("timestamp")),
            **values, "source": "iot", "received_at": now_utc()}


def create_alerts_if_needed(m):
    settings = db.session.get(Setting, m.device_id)
    rules = [
        ("high_power", m.power_w > (settings.power_limit_w if settings else 1600), "warning", "Daya tinggi", "Daya melampaui batas yang diatur."),
        ("low_voltage", m.voltage_v < (settings.voltage_min_v if settings else 200), "danger", "Tegangan rendah", "Tegangan berada di bawah ambang aman yang dikonfigurasi."),
        ("high_voltage", m.voltage_v > (settings.voltage_max_v if settings else 240), "danger", "Tegangan tinggi", "Tegangan berada di atas ambang aman yang dikonfigurasi."),
    ]
    from datetime import timedelta
    for category, triggered, severity, title, message in rules:
        if not triggered:
            continue
        recent = Alert.query.filter(Alert.device_id == m.device_id, Alert.category == category,
                                    Alert.timestamp >= m.timestamp - timedelta(minutes=30)).first()
        if recent:
            continue
        db.session.add(Alert(device_id=m.device_id, timestamp=m.timestamp, category=category,
                             severity=severity, title=title, message=message,
                             status="new", source=m.source))


def create_app(test_config=None, db_override=None):
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=os.getenv("SECRET_KEY", "change-this-only-for-local-development"),
        SQLALCHEMY_DATABASE_URI=sqlalchemy_database_url(os.getenv(
            "DATABASE_URL", "postgresql+psycopg://arus:arus_password@localhost:5432/arus_energy"
        )),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SQLALCHEMY_ENGINE_OPTIONS={"pool_pre_ping": True},
        DEFAULT_DEVICE_ID=os.getenv("DEFAULT_DEVICE_ID", "esp32-s3-01"),
        IOT_API_KEY=os.getenv("IOT_API_KEY", "development-iot-key-change-me"),
        AUTO_SEED_DEMO=is_true(os.getenv("AUTO_SEED_DEMO", "true")),
        DEMO_MODE=is_true(os.getenv("DEMO_MODE", "true")),
        MAX_CONTENT_LENGTH=64 * 1024,
        JSON_SORT_KEYS=False,
    )
    if test_config:
        app.config.update(test_config)
    if db_override is not None:
        app.config["SQLALCHEMY_DATABASE_URI"] = db_override
    db.init_app(app)
    try:
        with app.app_context():
            db.create_all()
            if app.config["AUTO_SEED_DEMO"]:
                seed_database(device_id=app.config["DEFAULT_DEVICE_ID"], reset=False)
    except SQLAlchemyError as exc:
        app.logger.warning("PostgreSQL belum tersedia: %s", exc)

    @app.errorhandler(SQLAlchemyError)
    def db_error(error):
        app.logger.error("Database error: %s", error)
        db.session.rollback()
        return json_error("PostgreSQL tidak tersambung. Jalankan: docker compose up --build", 503)

    @app.errorhandler(413)
    def too_large(_error):
        return json_error("Ukuran JSON melebihi batas.", 413)

    @app.route("/")
    def landing():
        return render_template("landing.html")

    @app.route("/dashboard")
    def dashboard():
        return render_template("dashboard.html", device_id=app.config["DEFAULT_DEVICE_ID"],
                               demo_mode=app.config["DEMO_MODE"])

    @app.get("/api/health")
    def health():
        try:
            db.session.execute(text("SELECT 1"))
            return jsonify({"status": "ok", "database": "connected", "time": to_iso(now_utc())})
        except SQLAlchemyError:
            db.session.rollback()
            return json_error("database unavailable", 503)

    @app.get("/api/devices")
    def devices():
        rows = Device.query.order_by(Device.device_id.asc()).all()
        result = [{"device_id": d.device_id, "name": d.name, "location": d.location,
                   "last_seen": to_iso(d.last_seen), "source": d.source} for d in rows]
        return jsonify({"devices": result})

    @app.get("/api/overview")
    def overview():
        try:
            device_id = current_device()
            period = request.args.get("period", "24h")
            if period not in ("24h", "7d", "30d"):
                return json_error("period harus 24h, 7d atau 30d.")
            return jsonify(get_dashboard_data(device_id, period))
        except ValueError as exc:
            return json_error(str(exc))

    @app.get("/api/history")
    def history():
        try:
            limit = min(max(int(request.args.get("limit", "12")), 1), 100)
            return jsonify({"data": get_history(current_device(), limit)})
        except ValueError:
            return json_error("limit harus bilangan bulat 1–100.")


    @app.get("/api/export.csv")
    def export_csv():
        import csv
        from io import StringIO
        from datetime import timedelta
        try:
            device_id = current_device()
            period = request.args.get("period", "30d")
            if period not in ("24h", "7d", "30d"):
                raise ValueError("period harus 24h, 7d, atau 30d.")
        except ValueError as exc:
            return json_error(str(exc))
        days = {"24h": 1, "7d": 7, "30d": 30}[period]
        since = now_utc() - timedelta(days=days)
        rows = (Measurement.query.filter(Measurement.device_id == device_id, Measurement.timestamp >= since)
                .order_by(Measurement.timestamp.desc()).limit(10000).all())
        stream = StringIO()
        writer = csv.writer(stream)
        writer.writerow(["timestamp_utc", "device_id", "voltage_v", "current_a", "power_w",
                         "energy_kwh", "frequency_hz", "power_factor", "source"])
        for m in rows:
            writer.writerow([to_iso(m.timestamp), m.device_id, m.voltage_v, m.current_a,
                             m.power_w, m.energy_kwh, m.frequency_hz, m.power_factor, m.source or "unknown"])
        response = Response("\ufeff" + stream.getvalue(), mimetype="text/csv; charset=utf-8")
        response.headers["Content-Disposition"] = f'attachment; filename="arus-{device_id}-{period}.csv"'
        return response

    @app.post("/api/alerts/<alert_id>/ack")
    def acknowledge_alert(alert_id):
        try:
            parsed_id = int(alert_id)
        except ValueError:
            return json_error("ID alert tidak valid.")
        alert = db.session.get(Alert, parsed_id)
        if alert is None:
            return json_error("Alert tidak ditemukan.", 404)
        alert.status = "acknowledged"
        db.session.commit()
        return jsonify({"message": "Alert ditandai sudah dibaca."})

    @app.route("/api/settings", methods=["GET", "PUT"])
    def settings():
        try:
            device_id = current_device()
            defaults = {"tariff_per_kwh": 1444.70, "power_limit_w": 1600,
                        "voltage_min_v": 200, "voltage_max_v": 240}
            if request.method == "GET":
                record = db.session.get(Setting, device_id)
                return jsonify({"device_id": device_id, **{
                    k: getattr(record, k) if record else v for k, v in defaults.items()
                }})
            payload = request.get_json(silent=True)
            if not isinstance(payload, dict):
                raise ValueError("Body harus berupa JSON object.")
            clean = {}
            for field, (lower, upper) in {
                "tariff_per_kwh": (0, 100000), "power_limit_w": (1, 25000),
                "voltage_min_v": (1, 299), "voltage_max_v": (2, 300)
            }.items():
                val = payload.get(field)
                import math
                if isinstance(val, bool) or not isinstance(val, (float, int)) or not math.isfinite(val) or not lower <= val <= upper:
                    raise ValueError(f"{field} harus angka dalam rentang {lower}–{upper}.")
                clean[field] = round(float(val), 2)
            if clean["voltage_min_v"] >= clean["voltage_max_v"]:
                raise ValueError("Tegangan minimum harus lebih kecil dari maksimum.")
            record = db.session.get(Setting, device_id)
            if record is None:
                record = Setting(device_id=device_id)
                db.session.add(record)
            for field, value in clean.items():
                setattr(record, field, value)
            db.session.commit()
            return jsonify({"message": "Pengaturan tersimpan.", "settings": {"device_id": device_id, **clean}})
        except ValueError as exc:
            return json_error(str(exc))

    @app.post("/api/ingest")
    @require_iot_key
    def ingest():
        try:
            doc = validate_measurement(request.get_json(silent=True))
        except ValueError as exc:
            return json_error(str(exc), 422)
        measurement = Measurement(**doc)
        db.session.add(measurement)
        try:
            db.session.flush()
        except IntegrityError:
            db.session.rollback()
            return json_error("Data timestamp ini sudah diterima (duplikat).", 409)
        device_id = doc["device_id"]
        device = db.session.get(Device, device_id)
        if device is None:
            device = Device(device_id=device_id, name="IoT Energy Meter", location="Belum ditentukan")
            db.session.add(device)
        device.last_seen = doc["timestamp"]
        device.source = "iot"
        create_alerts_if_needed(measurement)
        db.session.commit()
        return jsonify({"message": "Measurement tersimpan.", "device_id": device_id,
                        "timestamp": to_iso(doc["timestamp"])}), 201

    @app.post("/api/demo/tick")
    def demo_tick():
        if not app.config["DEMO_MODE"]:
            return json_error("Demo mode dinonaktifkan.", 403)
        import random
        from datetime import timedelta
        device_id = app.config["DEFAULT_DEVICE_ID"]
        latest = Measurement.query.filter_by(device_id=device_id).order_by(Measurement.timestamp.desc()).first()
        now = now_utc()
        if latest and latest.timestamp >= now:
            now = latest.timestamp + timedelta(microseconds=1)
        hour = now.hour
        base = 310 if hour < 6 else 620 if hour < 18 else 850
        power = max(85, min(1900, base + random.gauss(0, 145)))
        voltage = max(202, min(243, 223 + random.gauss(0, 2.8)))
        factor = 0.94
        elapsed_h = min(max((now - latest.timestamp).total_seconds() / 3600, 0.001), 0.25) if latest else 0.001
        total = (latest.energy_kwh if latest else 100.0) + power / 1000 * elapsed_h
        measurement = Measurement(device_id=device_id, timestamp=now, power_w=round(power, 2),
                       voltage_v=round(voltage, 2), current_a=round(power / max(voltage * factor, 1), 3),
                       energy_kwh=round(total, 5), frequency_hz=round(50 + random.gauss(0, .04), 2),
                       power_factor=factor, source="demo", received_at=now)
        db.session.add(measurement)
        device = db.session.get(Device, device_id)
        if device is None:
            device = Device(device_id=device_id, name="IoT Energy Meter", location="Belum ditentukan")
            db.session.add(device)
        device.last_seen = now
        device.source = "demo"
        create_alerts_if_needed(measurement)
        db.session.commit()
        return jsonify({"message": "Simulasi pembacaan baru berhasil.", "timestamp": to_iso(now)})

    @app.post("/api/demo/reset")
    def demo_reset():
        if not app.config["DEMO_MODE"]:
            return json_error("Demo mode dinonaktifkan.", 403)
        result = seed_database(device_id=app.config["DEFAULT_DEVICE_ID"], reset=True)
        return jsonify({"message": "Data demo dibuat ulang.", "count": result})

    return app
