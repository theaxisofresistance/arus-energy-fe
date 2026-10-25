/*
 * Versi ESP8266 dari examples/send_iot.py.
 * Mengirim data listrik dummy acak ke API ingest ARUS setiap 30 detik.
 */

#include <ESP8266HTTPClient.h>
#include <ESP8266WiFi.h>
#include <WiFiClientSecureBearSSL.h>

// Ganti konfigurasi berikut sebelum upload.
const char* WIFI_SSID = "NAMA_WIFI";
const char* WIFI_PASSWORD = "PASSWORD_WIFI";

// Gunakan URL HTTPS final, tanpa slash setelah /api/ingest.
// Contoh: https://arus-energy.example.com/api/ingest
const char* INGEST_URL = "https://GANTI-DOMAIN/api/ingest";
const char* API_KEY = "development-iot-key-change-me";
const char* DEVICE_ID = "esp8266-dummy-01";

const unsigned long SEND_INTERVAL_MS = 30000;
const unsigned long WIFI_RETRY_INTERVAL_MS = 10000;

unsigned long lastSendAt = 0;
unsigned long lastWifiRetryAt = 0;
float cumulativeEnergyKwh = 100.0f;

float randomFloat(float minimum, float maximum) {
  return minimum + (maximum - minimum) * (random(0, 10001) / 10000.0f);
}

void connectWifi() {
  if (WiFi.status() == WL_CONNECTED) {
    return;
  }

  Serial.printf("Menghubungkan ke Wi-Fi %s", WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  const unsigned long startedAt = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - startedAt < 15000) {
    delay(500);
    Serial.print('.');
    yield();
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("\nTersambung. IP ESP8266: %s\n",
                  WiFi.localIP().toString().c_str());
  } else {
    Serial.println("\nBelum tersambung; akan dicoba lagi.");
  }
}

String createDummyPayload() {
  const float voltage = randomFloat(218.0f, 228.0f);
  const float current = randomFloat(0.25f, 5.0f);
  const float powerFactor = randomFloat(0.88f, 0.99f);
  const float power = voltage * current * powerFactor;
  const float frequency = randomFloat(49.85f, 50.15f);

  const float elapsedHours = SEND_INTERVAL_MS / 3600000.0f;
  cumulativeEnergyKwh += (power / 1000.0f) * elapsedHours;

  String json;
  json.reserve(240);
  json += F("{\"device_id\":\"");
  json += DEVICE_ID;
  json += F("\",\"voltage_v\":");
  json += String(voltage, 2);
  json += F(",\"current_a\":");
  json += String(current, 3);
  json += F(",\"power_w\":");
  json += String(power, 2);
  json += F(",\"energy_kwh\":");
  json += String(cumulativeEnergyKwh, 5);
  json += F(",\"frequency_hz\":");
  json += String(frequency, 2);
  json += F(",\"power_factor\":");
  json += String(powerFactor, 3);
  json += '}';
  return json;
}

void sendMeasurement() {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("Pengiriman dilewati: Wi-Fi terputus.");
    return;
  }

  BearSSL::WiFiClientSecure client;

  // Mode demo: koneksi dienkripsi, tetapi sertifikat server belum diverifikasi.
  // Untuk produksi, ganti dengan validasi CA menggunakan setTrustAnchors().
  client.setInsecure();
  client.setBufferSizes(512, 512);

  HTTPClient http;
  http.setTimeout(10000);
  http.setFollowRedirects(HTTPC_STRICT_FOLLOW_REDIRECTS);

  if (!http.begin(client, INGEST_URL)) {
    Serial.println("Gagal membuka koneksi HTTPS.");
    return;
  }

  const String payload = createDummyPayload();
  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-API-Key", API_KEY);

  Serial.println("Mengirim: " + payload);
  const int statusCode = http.POST(payload);

  if (statusCode > 0) {
    const String response = http.getString();
    Serial.printf("HTTP %d: %s\n", statusCode, response.c_str());
  } else {
    Serial.printf("Gagal mengirim: %s\n",
                  HTTPClient::errorToString(statusCode).c_str());
  }

  http.end();
}

void setup() {
  Serial.begin(115200);
  Serial.println();

  randomSeed(ESP.getChipId() ^ micros() ^ analogRead(A0));
  WiFi.persistent(false);
  WiFi.setAutoReconnect(true);
  connectWifi();

  if (WiFi.status() == WL_CONNECTED) {
    sendMeasurement();
  }
  lastSendAt = millis();
}

void loop() {
  const unsigned long now = millis();

  if (WiFi.status() != WL_CONNECTED &&
      now - lastWifiRetryAt >= WIFI_RETRY_INTERVAL_MS) {
    lastWifiRetryAt = now;
    connectWifi();
  }

  if (now - lastSendAt >= SEND_INTERVAL_MS) {
    lastSendAt = now;
    sendMeasurement();
  }

  delay(10);
}
