"""Relational database models for ARUS."""
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import Index, UniqueConstraint


db = SQLAlchemy()


class Device(db.Model):
    __tablename__ = "devices"

    device_id = db.Column(db.String(64), primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    location = db.Column(db.String(160), nullable=False)
    last_seen = db.Column(db.DateTime, nullable=True)
    source = db.Column(db.String(20), nullable=False, default="unknown")


class Measurement(db.Model):
    __tablename__ = "measurements"
    __table_args__ = (
        UniqueConstraint("device_id", "timestamp", name="uq_measurement_device_timestamp"),
        Index("ix_measurement_device_timestamp", "device_id", "timestamp"),
    )

    id = db.Column(db.BigInteger().with_variant(db.Integer, "sqlite"), primary_key=True, autoincrement=True)
    device_id = db.Column(db.String(64), nullable=False, index=True)
    timestamp = db.Column(db.DateTime, nullable=False)
    voltage_v = db.Column(db.Float, nullable=False)
    current_a = db.Column(db.Float, nullable=False)
    power_w = db.Column(db.Float, nullable=False)
    energy_kwh = db.Column(db.Float, nullable=False)
    frequency_hz = db.Column(db.Float, nullable=False)
    power_factor = db.Column(db.Float, nullable=False)
    source = db.Column(db.String(20), nullable=False, default="unknown")
    received_at = db.Column(db.DateTime, nullable=False)


class Setting(db.Model):
    __tablename__ = "settings"

    device_id = db.Column(db.String(64), primary_key=True)
    tariff_per_kwh = db.Column(db.Float, nullable=False, default=1444.70)
    power_limit_w = db.Column(db.Float, nullable=False, default=1600)
    voltage_min_v = db.Column(db.Float, nullable=False, default=200)
    voltage_max_v = db.Column(db.Float, nullable=False, default=240)


class Alert(db.Model):
    __tablename__ = "alerts"
    __table_args__ = (Index("ix_alert_device_timestamp", "device_id", "timestamp"),)

    id = db.Column(db.BigInteger().with_variant(db.Integer, "sqlite"), primary_key=True, autoincrement=True)
    device_id = db.Column(db.String(64), nullable=False, index=True)
    timestamp = db.Column(db.DateTime, nullable=False)
    title = db.Column(db.String(160), nullable=False)
    message = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(60), nullable=False)
    severity = db.Column(db.String(20), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="new")
    source = db.Column(db.String(20), nullable=False, default="unknown")
