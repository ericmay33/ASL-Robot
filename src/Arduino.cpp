#include <Arduino.h>
#include <VarSpeedServo.h>
#include <ArduinoJson.h>

// ===== CONFIG =====
#define SERVO_COUNT 5      // Number of servos in use
#define MAX_QUEUE 3          // Buffer up to 3 signs
#define DEFAULT_SPEED 225    // Servo move speed (1–255)
#define BAUD_RATE 115200     // Match Python serial speed

// ===== GLOBALS =====
VarSpeedServo servos[MAX_SERVOS];
int servoPins[MAX_SERVOS] = {2, 3, 4, 5, 6};  // Adjust to your pin setup

String commandQueue[MAX_QUEUE];
int queueHead = 0, queueTail = 0, queueCount = 0;

// ===== FUNCTION DECLARATIONS =====
void enqueueCommand(const String &cmd);
bool dequeueCommand(String &cmd);
void processNextCommand();

// ===== SETUP =====
void setup() {
  Serial.begin(BAUD_RATE);
  delay(1000);

  Serial.println("\n[ESP32] Booting...");

  for (int i = 0; i < MAX_SERVOS; i++) {
    servos[i].attach(servoPins[i]);
    servos[i].write(90);  // neutral starting position
  }
  Serial.println("[ESP32] Ready — waiting for motion commands (VarSpeedServo active)");
}

// ===== MAIN LOOP =====
void loop() {
  // Check for incoming serial data (JSON)
  if (Serial.available()) {
    String input = Serial.readStringUntil('\n');
    input.trim();
    if (input.length() > 0) {
      enqueueCommand(input);
    }
  }

  // If we have queued commands, execute one at a time
  if (queueCount > 0) {
    processNextCommand();
  }
}

// ===== QUEUE MANAGEMENT =====
void enqueueCommand(const String &cmd) {
  if (queueCount < MAX_QUEUE) {
    commandQueue[queueTail] = cmd;
    queueTail = (queueTail + 1) % MAX_QUEUE;
    queueCount++;
    Serial.println("[ESP32] Added command to queue");
  } else {
    Serial.println("[ESP32] ⚠ Queue full, discarding command!");
  }
}

bool dequeueCommand(String &cmd) {
  if (queueCount > 0) {
    cmd = commandQueue[queueHead];
    queueHead = (queueHead + 1) % MAX_QUEUE;
    queueCount--;
    return true;
  }
  return false;
}

// ===== PROCESS COMMAND =====
void processNextCommand() {
  String jsonCmd;
  if (!dequeueCommand(jsonCmd)) return;

  StaticJsonDocument<512> doc;
  DeserializationError err = deserializeJson(doc, jsonCmd);

  if (err) {
    Serial.print("[ESP32] ❌ JSON parse error: ");
    Serial.println(err.c_str());
    return;
  }

  const char* token = doc["token"];
  JsonArray keyframes = doc["keyframes"];
  float duration = doc["duration"] | 1.0;

  Serial.print("[ESP32] Executing sign:");
  Serial.println(token);

  // Process keyframes one by one
  int frameCount = keyframes.size();
  if (frameCount == 0) {
    Serial.println("[ESP32] ⚠ No keyframes found.");
    return;
  }

  for (JsonObject frame : keyframes) {
    JsonArray L = frame["L"];  // Using your current schema (no speed)

    Serial.print("  [Frame ");
    Serial.print("] -> ");

    int i = 0;
    for (JsonVariant val : L) {
      if (i < MAX_SERVOS) {
        int targetAngle = val.as<int>();
        servos[i].write(targetAngle, DEFAULT_SPEED, false); // smooth move
        Serial.print(targetAngle);
        Serial.print(" ");
      }
      i++;
    }
    Serial.println();

    delay((duration * 1000) / frameCount);  // evenly divide total duration
  }
  Serial.println("ACK");  // Python waits for this before sending next
}