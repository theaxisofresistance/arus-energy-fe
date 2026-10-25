/*
 * ESP32-S3 + 2 potensiometer (Wokwi) -> API ARUS.
 *
 * Pot voltage: GPIO 4
 * Pot current: GPIO 5
 * UART1 RX/TX : GPIO 18/GPIO 17
 *
 * Data sensor ditampilkan setiap 1 detik dan dikirim ke /api/ingest
 * setiap 30 detik. Timestamp sengaja tidak dikirim agar server yang
 * memberikan waktu UTC dan sketch tidak perlu menunggu sinkronisasi NTP.
 */

#include <Arduino.h>
#include <HTTPClient.h>
#include <HardwareSerial.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>

#define POT_VOLTAGE 4
#define POT_CURRENT 5

HardwareSerial MySerial(1);

// Wokwi menyediakan access point ini tanpa password.
// Untuk board fisik, ganti dengan SSID dan password Wi-Fi Anda.
const char* WIFI_SSID = "Wokwi-GUEST";
const char* WIFI_PASSWORD = "";

// Ganti dengan URL deployment ARUS yang bisa diakses dari internet.
// Contoh: https://arus-energy.example.com/api/ingest
// Jangan gunakan localhost: localhost pada ESP menunjuk ke ESP itu sendiri.
const char* INGEST_URL = "https://GANTI-DOMAIN/api/ingest";
const char* API_KEY = "development-iot-key-change-me";
const char* DEVICE_ID = "esp32-s3-01";

const unsigned long READ_INTERVAL_MS = 1000;
const unsigned long SEND_INTERVAL_MS = 30000;
const unsigned long WIFI_RETRY_INTERVAL_MS = 10000;

unsigned long previousEnergyMs = 0;
unsigned long lastReadAt = 0;
unsigned long lastSendAt = 0;
unsigned long lastWifiRetryAt = 0;

float energyKWh = 0.0f;
float voltage = 0.0f;
float current = 0.0f;
float power = 0.0f;
const float powerFactor = 0.95f;
const float frequency = 50.0f;

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
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("\nTersambung. IP ESP32-S3: %s\n",
                  WiFi.localIP().toString().c_str());
  } else {
    Serial.println("\nBelum tersambung; akan dicoba lagi.");
  }
}

void readMeasurement(unsigned long now) {
  const int rawV = analogRead(POT_VOLTAGE);
  const int rawI = analogRead(POT_CURRENT);

  // Simulasi tegangan 180-250 V dan arus 0-10 A.
  voltage = 180.0f + (rawV / 4095.0f) * 70.0f;
  current = (rawI / 4095.0f) * 10.0f;
  power = voltage * current * powerFactor;

  // Integrasi daya terhadap waktu menghasilkan counter kWh kumulatif.
  const float elapsedHours = (now - previousEnergyMs) / 3600000.0f;
  energyKWh += (power * elapsedHours) / 1000.0f;
  previousEnergyMs = now;

  MySerial.println("--------------------------------");
  MySerial.printf("Voltage      : %.2f V\n", voltage);
  MySerial.printf("Current      : %.2f A\n", current);
  MySerial.printf("Power        : %.2f W\n", power);
  MySerial.printf("Energy       : %.6f kWh\n", energyKWh);
  MySerial.printf("Frequency    : %.2f Hz\n", frequency);
  MySerial.printf("Power Factor : %.2f\n", powerFactor);

  if (power > 1500.0f) {
    MySerial.println("Status       : WARNING - HIGH POWER");
  } else {
    MySerial.println("Status       : NORMAL");
  }

  // Serial adalah console bawaan Wokwi. UART1 tetap tersedia pada pin 17/18.
  Serial.printf("V=%.2f V | I=%.2f A | P=%.2f W | E=%.6f kWh\n",
                voltage, current, power, energyKWh);
}

String createPayload() {
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
  json += String(energyKWh, 6);
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

  WiFiClientSecure client;

  // Cocok untuk demo Wokwi. Untuk produksi, verifikasi sertifikat dengan CA.
  client.setInsecure();

  HTTPClient http;
  http.setTimeout(10000);
  http.setFollowRedirects(HTTPC_STRICT_FOLLOW_REDIRECTS);

  if (!http.begin(client, INGEST_URL)) {
    Serial.println("Gagal membuka koneksi HTTPS.");
    return;
  }

  const String payload = createPayload();
  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-API-Key", API_KEY);

  Serial.println("Mengirim: " + payload);
  const int statusCode = http.POST(payload);

  if (statusCode > 0) {
    Serial.printf("HTTP %d: %s\n", statusCode,
                  http.getString().c_str());
  } else {
    Serial.printf("Gagal mengirim: %s\n",
                  HTTPClient::errorToString(statusCode).c_str());
  }

  http.end();
}

void setup() {
  Serial.begin(115200);
  MySerial.begin(115200, SERIAL_8N1, 18, 17);

  analogReadResolution(12);
  pinMode(POT_VOLTAGE, INPUT);
  pinMode(POT_CURRENT, INPUT);

  WiFi.setAutoReconnect(true);
  WiFi.persistent(false);

  delay(500);
  Serial.println();
  MySerial.println("================================");
  MySerial.println("ENERGY MONITORING - ESP32-S3");
  MySerial.println("PZEM-004T SIMULATION + ARUS API");
  MySerial.println("================================");

  previousEnergyMs = millis();
  connectWifi();

  const unsigned long now = millis();
  readMeasurement(now);
  lastReadAt = now;

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

  if (now - lastReadAt >= READ_INTERVAL_MS) {
    lastReadAt = now;
    readMeasurement(now);
  }

  if (now - lastSendAt >= SEND_INTERVAL_MS) {
    lastSendAt = now;
    sendMeasurement();
  }

  delay(10);
}
