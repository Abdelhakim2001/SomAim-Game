#include <WiFi.h>
#include <WebSocketsClient.h>
#include <ArduinoJson.h>

// ── CONFIG ──────────────────────────────────────────
const char* SSID     = "Wifi-institut ismagi 5G";
const char* PASSWORD = "ismagi2024@";
const char* WS_HOST  = "192.168.100.217";
const int   WS_PORT  = 8765;

// ── AD8232 PINS (de ton collègue) ───────────────────
const int ADC_PIN  = 34;
const int LO_PLUS  = 19;
const int LO_MINUS = 18;

// ── BPM DETECTION ───────────────────────────────────
const int   THRESHOLD     = 3000;
unsigned long lastBeatTime = 0;
unsigned long lastSend     = 0;
float bpm                  = 0;
String heartStatus         = "Normal";

// ── WEBSOCKET ────────────────────────────────────────
WebSocketsClient ws;
const int SAMPLE_INTERVAL = 10; // 100Hz

void setup() {
  Serial.begin(115200);
  pinMode(ADC_PIN,  INPUT);
  pinMode(LO_PLUS,  INPUT);
  pinMode(LO_MINUS, INPUT);

  // WiFi
  WiFi.begin(SSID, PASSWORD);
  Serial.print("Connecting WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500); Serial.print(".");
  }
  Serial.println("\nWiFi Connected: " + WiFi.localIP().toString());

  // WebSocket
  ws.begin(WS_HOST, WS_PORT, "/ecg");
  ws.onEvent(wsEventHandler);
  ws.setReconnectInterval(3000);
}

void loop() {
  ws.loop();

  unsigned long now = millis();
  if (now - lastSend >= SAMPLE_INTERVAL) {
    lastSend = now;

    // Electrodes déconnectées
    if (digitalRead(LO_PLUS) == HIGH || digitalRead(LO_MINUS) == HIGH) {
      Serial.println("NOT CONNECTED");
      sendECG(-1, 0, "Disconnected", false);
      return;
    }

    int rawValue = analogRead(ADC_PIN);

    // ── Détection BPM (code collègue) ───────────────
    if (rawValue > THRESHOLD) {
      unsigned long timeBetweenBeats = now - lastBeatTime;
      if (timeBetweenBeats > 250) {
        bpm = 60000.0 / timeBetweenBeats;
        lastBeatTime = now;

        // Health Status
        if (bpm > 105) {
          heartStatus = "High";
          Serial.print("BPM: "); Serial.print(bpm); Serial.println(" -> High!");
        } else if (bpm < 60) {
          heartStatus = "Low";
          Serial.print("BPM: "); Serial.print(bpm); Serial.println(" -> Low!");
        } else {
          heartStatus = "Normal";
          Serial.print("BPM: "); Serial.print(bpm); Serial.println(" -> Normal");
        }
      }
    }

    // Envoyer tout au serveur Python
    sendECG(rawValue, bpm, heartStatus, true);
  }
}

// ── SEND ─────────────────────────────────────────────
void sendECG(int ecgValue, float bpmValue, String status, bool connected) {
  StaticJsonDocument<200> doc;
  doc["ecg"]          = ecgValue;
  doc["bpm"]          = bpmValue;
  doc["heart_status"] = status;       // "High" / "Normal" / "Low"
  doc["connected"]    = connected;
  doc["ts"]           = millis();

  String json;
  serializeJson(doc, json);
  ws.sendTXT(json);
}

// ── WS EVENTS ────────────────────────────────────────
void wsEventHandler(WStype_t type, uint8_t* payload, size_t length) {
  switch (type) {
    case WStype_CONNECTED:
      Serial.println("WebSocket Connected!"); break;
    case WStype_DISCONNECTED:
      Serial.println("WebSocket Disconnected"); break;
    case WStype_TEXT:
      Serial.printf("Server: %s\n", payload); break;
  }
}