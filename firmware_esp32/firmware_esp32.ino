/*
 * =========================================================================================
 * AI-BASED FASTENER INSPECTION & SORTING SYSTEM - ESP32 EMBEDDED CONTROLLER FIRMWARE
 * =========================================================================================
 * Hardware Target: ESP32-WROOM-32 / ESP32 DevKit V1
 * Actuators:
 *   - Inspection Pad Tilt: MG996R Servo (PWM Pin GPIO 18)
 *   - Rotating Sorting Chute: MG996R Servo (PWM Pin GPIO 19)
 *   - Conveyor Stepper: NEMA 17 via TB6600 Driver (STEP Pin GPIO 22, DIR Pin GPIO 23, EN Pin GPIO 21)
 * Sensors:
 *   - Pad Part Presence IR Sensor: GPIO 34
 *   - Conveyor Transfer IR Sensor: GPIO 35
 * Communication:
 *   - USB Serial: 115200 baud (JSON command parser)
 *   - Wi-Fi: Access Point / Station TCP Socket Server on Port 8080
 * =========================================================================================
 */

#include <WiFi.h>
#include <ESP32Servo.h>
#include <ArduinoJson.h>

// Pin Definitions
#define PIN_PAD_SERVO       18
#define PIN_CHUTE_SERVO     19
#define PIN_STEPPER_STEP    22
#define PIN_STEPPER_DIR     23
#define PIN_STEPPER_EN      21
#define PIN_IR_PAD          34
#define PIN_IR_CONVEYOR     35
#define PIN_LED_STATUS      2

// Servo Objects
Servo padServo;
Servo chuteServo;

// Wi-Fi Configuration
const char* ap_ssid = "FastenerInspection-ESP32";
const char* ap_pass = "fastener123";
WiFiServer tcpServer(8080);
WiFiClient client;

// State Machine Variables
bool isEstopped = false;
int currentChuteAngle = 0;
int currentPadAngle = 0;
bool conveyorRunning = false;

void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.println("{\"status\":\"BOOTING\",\"firmware\":\"v1.0.0\"}");

  // Setup GPIOs
  pinMode(PIN_STEPPER_STEP, OUTPUT);
  pinMode(PIN_STEPPER_DIR, OUTPUT);
  pinMode(PIN_STEPPER_EN, OUTPUT);
  pinMode(PIN_LED_STATUS, OUTPUT);
  pinMode(PIN_IR_PAD, INPUT);
  pinMode(PIN_IR_CONVEYOR, INPUT);

  // Disable stepper driver initially
  digitalWrite(PIN_STEPPER_EN, HIGH); // Active LOW for TB6600

  // Attach Servos (500us - 2400us for MG996R)
  ESP32PWM::allocateTimer(0);
  ESP32PWM::allocateTimer(1);
  padServo.setPeriodHertz(50);
  chuteServo.setPeriodHertz(50);
  padServo.attach(PIN_PAD_SERVO, 500, 2400);
  chuteServo.attach(PIN_CHUTE_SERVO, 500, 2400);

  // Home Positions
  padServo.write(0);
  chuteServo.write(0);

  // Initialize Wi-Fi AP
  WiFi.softAP(ap_ssid, ap_pass);
  tcpServer.begin();

  digitalWrite(PIN_LED_STATUS, HIGH);
  Serial.println("{\"status\":\"READY\",\"ip\":\"192.168.4.1\"}");
}

void loop() {
  // Check USB Serial input
  if (Serial.available() > 0) {
    String line = Serial.readStringUntil('\n');
    line.trim();
    if (line.length() > 0) {
      processCommand(line);
    }
  }

  // Check Wi-Fi TCP Client
  if (!client || !client.connected()) {
    client = tcpServer.available();
  } else if (client.available() > 0) {
    String line = client.readStringUntil('\n');
    line.trim();
    if (line.length() > 0) {
      processCommand(line);
    }
  }

  delay(10);
}

void processCommand(String jsonStr) {
  StaticJsonDocument<512> doc;
  DeserializationError error = deserializeJson(doc, jsonStr);
  if (error) {
    Serial.println("{\"error\":\"INVALID_JSON\"}");
    return;
  }

  const char* cmd = doc["command"];
  if (!cmd) return;

  // EMERGENCY STOP COMMAND (Highest Priority)
  if (strcmp(cmd, "ESTOP") == 0) {
    isEstopped = true;
    digitalWrite(PIN_STEPPER_EN, HIGH); // Cut stepper power
    conveyorRunning = false;
    padServo.write(0);
    Serial.println("{\"ack\":\"ESTOP_ACTIVATED\",\"state\":\"EMERGENCY_STOP\"}");
    return;
  }

  if (strcmp(cmd, "RESET_ESTOP") == 0) {
    isEstopped = false;
    Serial.println("{\"ack\":\"ESTOP_RESET\",\"state\":\"READY\"}");
    return;
  }

  // If E-Stopped, reject all other commands
  if (isEstopped) {
    Serial.println("{\"error\":\"REJECTED_ESTOP_ACTIVE\"}");
    return;
  }

  // 1. SORT CHUTE POSITIONING
  if (strcmp(cmd, "SORT") == 0) {
    int angle = doc["angle"] | 0;
    int tray = doc["tray"] | 1;
    angle = constrain(angle, 0, 180);
    chuteServo.write(angle);
    currentChuteAngle = angle;
    sendAck("SORT", angle, tray);
  }
  // 2. PAD TILT SERVO
  else if (strcmp(cmd, "TILT_PAD") == 0) {
    int angle = doc["angle"] | 0;
    angle = constrain(angle, 0, 90);
    padServo.write(angle);
    currentPadAngle = angle;
    sendAck("TILT_PAD", angle, 0);
  }
  // 3. CONVEYOR STEPPER RUN
  else if (strcmp(cmd, "CONVEYOR") == 0) {
    const char* act = doc["action"];
    if (strcmp(act, "RUN") == 0) {
      int duration = doc["duration_ms"] | 1200;
      runConveyorStepper(duration);
      sendAck("CONVEYOR", 1, 0);
    } else {
      digitalWrite(PIN_STEPPER_EN, HIGH);
      conveyorRunning = false;
      sendAck("CONVEYOR", 0, 0);
    }
  }
  // 4. RESET ALL ACTUATORS HOME
  else if (strcmp(cmd, "RESET") == 0) {
    padServo.write(0);
    chuteServo.write(0);
    digitalWrite(PIN_STEPPER_EN, HIGH);
    currentPadAngle = 0;
    currentChuteAngle = 0;
    conveyorRunning = false;
    sendAck("RESET", 0, 0);
  }
  // 5. STATUS / TELEMETRY REQUEST
  else if (strcmp(cmd, "PING") == 0 || strcmp(cmd, "STATUS") == 0) {
    sendTelemetry();
  }
}

void runConveyorStepper(int duration_ms) {
  digitalWrite(PIN_STEPPER_EN, LOW); // Enable driver
  digitalWrite(PIN_STEPPER_DIR, HIGH); // Forward direction
  conveyorRunning = true;

  unsigned long startTime = millis();
  while (millis() - startTime < (unsigned long)duration_ms) {
    if (isEstopped) break;
    digitalWrite(PIN_STEPPER_STEP, HIGH);
    delayMicroseconds(600);
    digitalWrite(PIN_STEPPER_STEP, LOW);
    delayMicroseconds(600);
  }

  digitalWrite(PIN_STEPPER_EN, HIGH);
  conveyorRunning = false;
}

void sendAck(const char* cmd, int val, int tray) {
  StaticJsonDocument<256> resp;
  resp["ack"] = cmd;
  resp["value"] = val;
  resp["tray"] = tray;
  resp["state"] = isEstopped ? "EMERGENCY_STOP" : "READY";
  resp["ir_pad"] = digitalRead(PIN_IR_PAD) == LOW;
  resp["ir_conveyor"] = digitalRead(PIN_IR_CONVEYOR) == LOW;

  String out;
  serializeJson(resp, out);
  Serial.println(out);
  if (client && client.connected()) {
    client.println(out);
  }
}

void sendTelemetry() {
  StaticJsonDocument<256> resp;
  resp["state"] = isEstopped ? "EMERGENCY_STOP" : "READY";
  resp["chute_angle"] = currentChuteAngle;
  resp["pad_angle"] = currentPadAngle;
  resp["conveyor"] = conveyorRunning;
  resp["wifi"] = WiFi.status() == WL_CONNECTED || WiFi.softAPgetStationNum() > 0;
  resp["usb"] = true;
  resp["battery_v"] = 12.35;

  String out;
  serializeJson(resp, out);
  Serial.println(out);
  if (client && client.connected()) {
    client.println(out);
  }
}
