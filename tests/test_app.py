from datetime import datetime, timedelta, timezone
import unittest

from app import create_app, sqlalchemy_database_url
from app.database import Alert, Measurement, db


class EnergyAppTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app({"TESTING": True, "AUTO_SEED_DEMO": True,
                               "IOT_API_KEY": "test-key", "DEMO_MODE": True,
                               "SQLALCHEMY_DATABASE_URI": "sqlite://",
                               "SQLALCHEMY_ENGINE_OPTIONS": {}})
        self.context = self.app.app_context()
        self.context.push()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def test_pages_and_health(self):
        self.assertEqual(self.client.get('/').status_code, 200)
        self.assertIn(b'Keputusan', self.client.get('/').data)
        dashboard = self.client.get('/dashboard')
        self.assertEqual(dashboard.status_code, 200)
        self.assertIn(b'id="deviceSelect"', dashboard.data)
        self.assertEqual(self.client.get('/api/health').json['status'], 'ok')

    def test_neon_database_url_uses_psycopg3(self):
        neon = 'postgresql://user:secret@example.neon.tech/neondb?sslmode=require'
        self.assertEqual(sqlalchemy_database_url(neon),
                         'postgresql+psycopg://user:secret@example.neon.tech/neondb?sslmode=require')

    def test_seed_and_overview(self):
        self.assertEqual(Measurement.query.count(), 2881)
        for period in ['24h', '7d', '30d']:
            response = self.client.get(f'/api/overview?period={period}')
            self.assertEqual(response.status_code, 200)
            data = response.json
            self.assertFalse(data['empty'])
            self.assertEqual(data['period'], period)
            self.assertGreater(data['stats']['energy_24h_kwh'], 0)
            self.assertGreater(data['stats']['cost_30d'], 0)
            self.assertEqual(len(data['forecast']['days']), 7)
            self.assertIn('voltage_v', data['latest'])
        self.assertEqual(self.client.get('/api/overview?period=year').status_code, 400)

    def test_ingest_auth_validation_duplicate(self):
        payload = {"device_id": "test-meter", "voltage_v": 220.0, "current_a": 2.0,
                   "power_w": 430.0, "energy_kwh": 12.5, "frequency_hz": 50.0,
                   "power_factor": .95, "timestamp": datetime.now(timezone.utc).replace(microsecond=0).isoformat()}
        self.assertEqual(self.client.post('/api/ingest', json=payload).status_code, 401)
        headers = {'X-API-Key': 'test-key'}
        self.assertEqual(self.client.post('/api/ingest', json=payload, headers=headers).status_code, 201)
        device_ids = [item['device_id'] for item in self.client.get('/api/devices').json['devices']]
        self.assertIn('test-meter', device_ids)
        self.assertEqual(self.client.post('/api/ingest', json=payload, headers=headers).status_code, 409)
        bad = {**payload, 'power_factor': 2}
        self.assertEqual(self.client.post('/api/ingest', json=bad, headers=headers).status_code, 422)
        payload2 = {**payload, 'timestamp': (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(), 'power_w': 1800}
        self.assertEqual(self.client.post('/api/ingest', json=payload2, headers=headers).status_code, 201)
        self.assertGreater(Alert.query.filter_by(device_id='test-meter').count(), 0)

    def test_settings_history_export_alerts_simulation(self):
        response = self.client.get('/api/settings')
        self.assertEqual(response.status_code, 200)
        settings = {"tariff_per_kwh": 1800, "power_limit_w": 1500,
                    "voltage_min_v": 200, "voltage_max_v": 245}
        self.assertEqual(self.client.put('/api/settings', json=settings).status_code, 200)
        self.assertEqual(self.client.get('/api/settings').json['tariff_per_kwh'], 1800)
        self.assertEqual(len(self.client.get('/api/history?limit=5').json['data']), 5)
        csv_res = self.client.get('/api/export.csv?period=24h')
        self.assertEqual(csv_res.status_code, 200)
        self.assertIn(b'timestamp_utc', csv_res.data)
        alert_id = self.client.get('/api/overview').json['alerts'][0]['id']
        self.assertEqual(self.client.post(f'/api/alerts/{alert_id}/ack').status_code, 200)
        self.assertEqual(self.client.post('/api/demo/tick').status_code, 200)
        self.assertEqual(self.client.post('/api/demo/reset').json['count'], 2881)

if __name__ == '__main__':
    unittest.main()
