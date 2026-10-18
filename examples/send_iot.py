"""Example publisher: replace the dummy payload with sensor readings from ESP32."""
import os
import json
from datetime import datetime, timezone
from urllib.request import Request, urlopen

payload = {
    "device_id": "esp32-s3-01",
    "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    "voltage_v": 221.8,
    "current_a": 2.15,
    "power_w": 448.3,
    "energy_kwh": 250.12345,  # cumulative kWh from PZEM-004T
    "frequency_hz": 50.01,
    "power_factor": 0.94,
}
url = os.getenv("ARUS_URL", "http://localhost:5000") + "/api/ingest"
key = os.getenv("IOT_API_KEY", "development-iot-key-change-me")
req = Request(url, data=json.dumps(payload).encode(), headers={
    "Content-Type": "application/json", "X-API-Key": key}, method="POST")
with urlopen(req, timeout=10) as response:
    print(response.status, response.read().decode())
