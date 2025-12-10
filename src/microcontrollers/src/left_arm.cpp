#include <Arduino.h>
#include <ESP32Servo.h>
#include <ArduinoJson.h>

// ================================
// CONFIGURATION
// ================================
// Left arm servos: Hand (5) + Wrist (2) + Elbow (1) + Shoulder (2) = 10 total
#define HAND_SERVO_COUNT 5
#define WRIST_SERVO_COUNT 2
#define ELBOW_SERVO_COUNT 1
#define SHOULDER_SERVO_COUNT 2
#define TOTAL_SERVO_COUNT 10

#define MAX_QUEUE 3            // command buffer size
#define BAUD_RATE 115200
#define DEFAULT_STEP_DELAY 2   // ms per movement step (reduced for smoother motion)

// ================================
// SERVO DECLARATIONS
// ================================
Servo handServos[HAND_SERVO_COUNT];
Servo wristServos[WRIST_SERVO_COUNT];
Servo elbowServos[ELBOW_SERVO_COUNT];
Servo shoulderServos[SHOULDER_SERVO_COUNT];

// Change these pins to your setup
// Hand servos (L)
int handPins[HAND_SERVO_COUNT] = {12, 14, 27, 26, 25};
// Wrist servos (LW)
int wristPins[WRIST_SERVO_COUNT] = {32, 33};
// Elbow servo (LE)
int elbowPins[ELBOW_SERVO_COUNT] = {22};
// Shoulder servos (LS)
int shoulderPins[SHOULDER_SERVO_COUNT] = {23, 25};

// ================================
// COMMAND QUEUE
// ================================
String commandQueue[MAX_QUEUE];
int queueHead = 0, queueTail = 0, queueCount = 0;

// ================================
// QUEUE HELPERS
// ================================
void enqueueCommand(const String &cmd) {
  if (queueCount < MAX_QUEUE) {
    commandQueue[queueTail] = cmd;
    queueTail = (queueTail + 1) % MAX_QUEUE;
    queueCount++;
    Serial.println("[LEFT_ARM] Command queued");
  } else {
    Serial.println("[LEFT_ARM] ⚠ Queue full, discarding command");
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

// ================================
// PROCESS ONE MOTION COMMAND
// ================================
void processCommand(String jsonCmd) {
  
  StaticJsonDocument<2048> doc;
  DeserializationError err = deserializeJson(doc, jsonCmd);

  if (err) {
    Serial.print("[LEFT_ARM] ❌ JSON Parse Error: ");
    Serial.println(err.c_str());
    return;
  }

  const char* token = doc["token"] | "<unknown>";
  float duration = doc["duration"] | 1.0f;

  Serial.print("[LEFT_ARM] Executing token: ");
  Serial.println(token);

  JsonArray keyframes = doc["keyframes"];
  int frameCount = keyframes.size();

  if (frameCount == 0) {
    Serial.println("[LEFT_ARM] ⚠ No keyframes!");
    return;
  }

  // Process each keyframe
  for (JsonObject frame : keyframes) {
    
    // Extract target angles
    int targetHandAngles[HAND_SERVO_COUNT];
    int targetWristAngles[WRIST_SERVO_COUNT];
    int targetElbowAngles[ELBOW_SERVO_COUNT];
    int targetShoulderAngles[SHOULDER_SERVO_COUNT];
    
    bool hasHand = false, hasWrist = false, hasElbow = false, hasShoulder = false;
    
    // Extract left-hand array (L)
    JsonArray L = frame["L"];
    if (!L.isNull() && L.size() == HAND_SERVO_COUNT) {
      for (int i = 0; i < HAND_SERVO_COUNT; i++) {
        targetHandAngles[i] = L[i].as<int>();
      }
      hasHand = true;
    }

    // Extract left-wrist array (LW)
    JsonArray LW = frame["LW"];
    if (!LW.isNull() && LW.size() == WRIST_SERVO_COUNT) {
      for (int i = 0; i < WRIST_SERVO_COUNT; i++) {
        targetWristAngles[i] = LW[i].as<int>();
      }
      hasWrist = true;
    }

    // Extract left-elbow array (LE)
    JsonArray LE = frame["LE"];
    if (!LE.isNull() && LE.size() == ELBOW_SERVO_COUNT) {
      for (int i = 0; i < ELBOW_SERVO_COUNT; i++) {
        targetElbowAngles[i] = LE[i].as<int>();
      }
      hasElbow = true;
    }

    // Extract left-shoulder array (LS)
    JsonArray LS = frame["LS"];
    if (!LS.isNull() && LS.size() == SHOULDER_SERVO_COUNT) {
      for (int i = 0; i < SHOULDER_SERVO_COUNT; i++) {
        targetShoulderAngles[i] = LS[i].as<int>();
      }
      hasShoulder = true;
    }

    // Smooth concurrent motion - move all servos together
    // Use local variables for current positions (no persistent storage)
    int currentHand[HAND_SERVO_COUNT];
    int currentWrist[WRIST_SERVO_COUNT];
    int currentElbow[ELBOW_SERVO_COUNT];
    int currentShoulder[SHOULDER_SERVO_COUNT];
    
    // Initialize from previous keyframe targets (or 90 if first frame)
    static int prevHand[HAND_SERVO_COUNT] = {90, 90, 90, 90, 90};
    static int prevWrist[WRIST_SERVO_COUNT] = {90, 90};
    static int prevElbow[ELBOW_SERVO_COUNT] = {90};
    static int prevShoulder[SHOULDER_SERVO_COUNT] = {90, 90};
    
    if (hasHand) {
      for (int i = 0; i < HAND_SERVO_COUNT; i++) {
        currentHand[i] = prevHand[i];
      }
    }
    if (hasWrist) {
      for (int i = 0; i < WRIST_SERVO_COUNT; i++) {
        currentWrist[i] = prevWrist[i];
      }
    }
    if (hasElbow) {
      for (int i = 0; i < ELBOW_SERVO_COUNT; i++) {
        currentElbow[i] = prevElbow[i];
      }
    }
    if (hasShoulder) {
      for (int i = 0; i < SHOULDER_SERVO_COUNT; i++) {
        currentShoulder[i] = prevShoulder[i];
      }
    }

    // Find max steps needed
    int maxSteps = 0;
    if (hasHand) {
      for (int i = 0; i < HAND_SERVO_COUNT; i++) {
        int steps = abs(targetHandAngles[i] - currentHand[i]);
        if (steps > maxSteps) maxSteps = steps;
      }
    }
    if (hasWrist) {
      for (int i = 0; i < WRIST_SERVO_COUNT; i++) {
        int steps = abs(targetWristAngles[i] - currentWrist[i]);
        if (steps > maxSteps) maxSteps = steps;
      }
    }
    if (hasElbow) {
      for (int i = 0; i < ELBOW_SERVO_COUNT; i++) {
        int steps = abs(targetElbowAngles[i] - currentElbow[i]);
        if (steps > maxSteps) maxSteps = steps;
      }
    }
    if (hasShoulder) {
      for (int i = 0; i < SHOULDER_SERVO_COUNT; i++) {
        int steps = abs(targetShoulderAngles[i] - currentShoulder[i]);
        if (steps > maxSteps) maxSteps = steps;
      }
    }

    // Move all servos concurrently
    for (int step = 0; step < maxSteps; step++) {
      // Update all positions, then write all servos together
      if (hasHand) {
        for (int i = 0; i < HAND_SERVO_COUNT; i++) {
          if (currentHand[i] != targetHandAngles[i]) {
            currentHand[i] += (currentHand[i] < targetHandAngles[i]) ? 1 : -1;
          }
          handServos[i].write(currentHand[i]);
        }
      }
      
      if (hasWrist) {
        for (int i = 0; i < WRIST_SERVO_COUNT; i++) {
          if (currentWrist[i] != targetWristAngles[i]) {
            currentWrist[i] += (currentWrist[i] < targetWristAngles[i]) ? 1 : -1;
          }
          wristServos[i].write(currentWrist[i]);
        }
      }
      
      if (hasElbow) {
        for (int i = 0; i < ELBOW_SERVO_COUNT; i++) {
          if (currentElbow[i] != targetElbowAngles[i]) {
            currentElbow[i] += (currentElbow[i] < targetElbowAngles[i]) ? 1 : -1;
          }
          elbowServos[i].write(currentElbow[i]);
        }
      }
      
      if (hasShoulder) {
        for (int i = 0; i < SHOULDER_SERVO_COUNT; i++) {
          if (currentShoulder[i] != targetShoulderAngles[i]) {
            currentShoulder[i] += (currentShoulder[i] < targetShoulderAngles[i]) ? 1 : -1;
          }
          shoulderServos[i].write(currentShoulder[i]);
        }
      }
      
      delay(DEFAULT_STEP_DELAY);
    }

    // Update previous positions for next keyframe
    if (hasHand) {
      for (int i = 0; i < HAND_SERVO_COUNT; i++) {
        prevHand[i] = targetHandAngles[i];
      }
    }
    if (hasWrist) {
      for (int i = 0; i < WRIST_SERVO_COUNT; i++) {
        prevWrist[i] = targetWristAngles[i];
      }
    }
    if (hasElbow) {
      for (int i = 0; i < ELBOW_SERVO_COUNT; i++) {
        prevElbow[i] = targetElbowAngles[i];
      }
    }
    if (hasShoulder) {
      for (int i = 0; i < SHOULDER_SERVO_COUNT; i++) {
        prevShoulder[i] = targetShoulderAngles[i];
      }
    }

    // Calculate frame time based on duration
    float frameTime = duration / frameCount;
    delay((int)(frameTime * 1000));
  }

  // Signal completion back to Python
  Serial.println("ACK");
}

// ================================
// SETUP
// ================================
void setup() {
  Serial.begin(BAUD_RATE);
  delay(1500);

  Serial.println("[LEFT_ARM] Booting...");

  // Attach hand servos
  for (int i = 0; i < HAND_SERVO_COUNT; i++) {
    handServos[i].attach(handPins[i]);
    handServos[i].write(90);
  }

  // Attach wrist servos
  for (int i = 0; i < WRIST_SERVO_COUNT; i++) {
    wristServos[i].attach(wristPins[i]);
    wristServos[i].write(90);
  }

  // Attach elbow servo
  for (int i = 0; i < ELBOW_SERVO_COUNT; i++) {
    elbowServos[i].attach(elbowPins[i]);
    elbowServos[i].write(90);
  }

  // Attach shoulder servos
  for (int i = 0; i < SHOULDER_SERVO_COUNT; i++) {
    shoulderServos[i].attach(shoulderPins[i]);
    shoulderServos[i].write(90);
  }

  Serial.println("[LEFT_ARM] Ready for motion commands.");
}

// ================================
// MAIN LOOP
// ================================
void loop() {

  // Receive new commands
  if (Serial.available()) {
    String input = Serial.readStringUntil('\n');
    input.trim();

    if (input.length() > 0) {
      enqueueCommand(input);
    }
  }

  // Handle queued commands
  if (queueCount > 0) {
    String cmd;
    if (dequeueCommand(cmd)) {
      processCommand(cmd);
    }
  }
}

