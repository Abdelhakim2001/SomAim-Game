// HeartAim ESP32 Firmware
// ECG via AD8232 → WebSocket WiFi → Python Backend

#include <WiFi.h>
#include <WebSocketsClient.h>
#include <ArduinoJson.h>

// ── CONFIG ──────────────────────────────────────────
const char* SSID     = "Wifi-institut ismagi 5G";
const char* PASSWORD = "ismagi2024@";
const char* WS_HOST  = "192.168.100.217"; // IP de ton PC
const int   WS_PORT  = 8765;

// AD8232 pins
const int ECG_PIN    = 34; // Analog input
const int LO_PLUS    = 32; // Leads-off detection +
const int LO_MINUS   = 33; // Leads-off detection -

WebSocketsClient ws;
unsigned long lastSend = 0;
const int SAMPLE_INTERVAL = 10; // 100Hz sampling

// ── SETUP ───────────────────────────────────────────
void setup() {
  Serial.begin(115200);
  pinMode(LO_PLUS,  INPUT);
  pinMode(LO_MINUS, INPUT);

  // Connect WiFi
  WiFi.begin(SSID, PASSWORD);
  Serial.print("Connecting WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500); Serial.print(".");
  }
  Serial.println("\nWiFi Connected: " + WiFi.localIP().toString());

  // Connect WebSocket
  ws.begin(WS_HOST, WS_PORT, "/ecg");
  ws.onEvent(wsEventHandler);
  ws.setReconnectInterval(3000);
}

// ── LOOP ────────────────────────────────────────────
void loop() {
  ws.loop();

  unsigned long now = millis();
  if (now - lastSend >= SAMPLE_INTERVAL) {
    lastSend = now;

    // Check leads-off
    if (digitalRead(LO_PLUS) || digitalRead(LO_MINUS)) {
      sendECG(-1, false); // Signal electrode déconnectée
      return;
    }

    int rawECG = analogRead(ECG_PIN);
    sendECG(rawECG, true);
  }
}

// ── SEND ECG ────────────────────────────────────────
void sendECG(int value, bool connected) {
  StaticJsonDocument<128> doc;
  doc["ecg"]       = value;
  doc["connected"] = connected;
  doc["ts"]        = millis();

  String json;
  serializeJson(doc, json);
  ws.sendTXT(json);
}

// ── WS EVENTS ───────────────────────────────────────
void wsEventHandler(WStype_t type, uint8_t* payload, size_t length) {
  switch (type) {
    case WStype_CONNECTED:
      Serial.println("WebSocket Connected!");
      break;
    case WStype_DISCONNECTED:
      Serial.println("WebSocket Disconnected");
      break;
    case WStype_TEXT:
      Serial.printf("Server: %s\n", payload);
      break;
  }
}