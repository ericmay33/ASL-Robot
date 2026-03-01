#include <Arduino.h>
#include <ESP32Servo.h>
#include <ArduinoJson.h>
#include <AccelStepper.h>

// ================================
// CONFIGURATION
// ================================
// Right arm servos: Hand (5) + Wrist (2) + Elbow (1) = 8 total
// Shoulder joints are stepper motors (A4988) — see SHOULDER STEPPER PINS below
#define HAND_SERVO_COUNT  5
#define WRIST_SERVO_COUNT 2
#define ELBOW_SERVO_COUNT 1
#define TOTAL_SERVO_COUNT 8

#define MAX_QUEUE          3
#define BAUD_RATE          115200
#define DEFAULT_STEP_DELAY 2   // ms per servo movement step

// Stepper calibration (both arms share same hardware, so same constants)
// Rotation axis — tune for actual gear ratio
#define ROTATION_STEPS_PER_DEG  320.0f
// Elevation axis — tune for actual gear ratio
#define ELEVATION_STEPS_PER_DEG 222.22f

#define SHOULDER_MAX_SPEED 10000.0f
#define SHOULDER_ACCEL     5000.0f

// ================================
// SERVO DECLARATIONS
// ================================
Servo handServos[HAND_SERVO_COUNT];
Servo wristServos[WRIST_SERVO_COUNT];
Servo elbowServos[ELBOW_SERVO_COUNT];

// Hand servos (R): Thumb, Index, Middle, Ring, Pinky
int handPins[HAND_SERVO_COUNT]   = {15, 2, 0, 4, 16};
// Wrist servos (RW): Rotation, Flexion
int wristPins[WRIST_SERVO_COUNT] = {18, 19};
// Elbow servo (RE)
int elbowPins[ELBOW_SERVO_COUNT] = {21};

// ================================
// SHOULDER STEPPER PINS
// ================================
// Motor 1: Shoulder Rotation (internal/external rotation)
// ⚠ GPIO 34 and 35 are INPUT-ONLY on standard ESP32 — replace if motor 1 does not move
const int shoulder1_dirPin    = 34;  // ⚠ INPUT-ONLY on ESP32 — swap to an output-capable GPIO
const int shoulder1_stepPin   = 35;  // ⚠ INPUT-ONLY on ESP32 — swap to an output-capable GPIO
const int shoulder1_ms1Pin    = 33;
const int shoulder1_ms2Pin    = 32;
const int shoulder1_enablePin = 25;

// Motor 2: Shoulder Elevation (raise/lower)
const int shoulder2_dirPin    = 26;
const int shoulder2_stepPin   = 27;
const int shoulder2_ms1Pin    = 12;
const int shoulder2_ms2Pin    = 14;
const int shoulder2_enablePin = 13;

// ================================
// SHOULDER STEPPER OBJECTS
// AccelStepper type 1 = DRIVER interface (STEP + DIR)
// ================================
AccelStepper shoulderRotation(1, shoulder1_stepPin, shoulder1_dirPin);
AccelStepper shoulderElevation(1, shoulder2_stepPin, shoulder2_dirPin);

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
    Serial.println("[RIGHT_ARM] Command queued");
  } else {
    Serial.println("[RIGHT_ARM] ⚠ Queue full, discarding command");
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
    Serial.print("[RIGHT_ARM] ❌ JSON Parse Error: ");
    Serial.println(err.c_str());
    return;
  }

  const char* token = doc["token"] | "<unknown>";
  float duration = doc["duration"] | 1.0f;

  Serial.print("[RIGHT_ARM] Executing token: ");
  Serial.println(token);

  JsonArray keyframes = doc["keyframes"];
  int frameCount = keyframes.size();

  if (frameCount == 0) {
    Serial.println("[RIGHT_ARM] ⚠ No keyframes!");
    return;
  }

  // Previous stepper positions in steps — persisted across keyframes
  static long prevRotationSteps  = 0;
  static long prevElevationSteps = 0;

  // Process each keyframe
  for (JsonObject frame : keyframes) {

    // Extract target servo angles
    int targetHandAngles[HAND_SERVO_COUNT];
    int targetWristAngles[WRIST_SERVO_COUNT];
    int targetElbowAngles[ELBOW_SERVO_COUNT];

    bool hasHand = false, hasWrist = false, hasElbow = false, hasShoulder = false;

    // Stepper targets default to previous position (no movement if RS absent)
    long targetRotationSteps  = prevRotationSteps;
    long targetElevationSteps = prevElevationSteps;

    // Extract right-hand array (R)
    JsonArray R = frame["R"];
    if (!R.isNull() && R.size() == HAND_SERVO_COUNT) {
      for (int i = 0; i < HAND_SERVO_COUNT; i++) {
        targetHandAngles[i] = R[i].as<int>();
      }
      hasHand = true;
    }

    // Extract right-wrist array (RW)
    JsonArray RW = frame["RW"];
    if (!RW.isNull() && RW.size() == WRIST_SERVO_COUNT) {
      for (int i = 0; i < WRIST_SERVO_COUNT; i++) {
        targetWristAngles[i] = RW[i].as<int>();
      }
      hasWrist = true;
    }

    // Extract right-elbow array (RE)
    JsonArray RE = frame["RE"];
    if (!RE.isNull() && RE.size() == ELBOW_SERVO_COUNT) {
      for (int i = 0; i < ELBOW_SERVO_COUNT; i++) {
        targetElbowAngles[i] = RE[i].as<int>();
      }
      hasElbow = true;
    }

    // Extract right-shoulder array (RS): [rotation_deg, elevation_deg]
    JsonArray RS = frame["RS"];
    if (!RS.isNull() && RS.size() == 2) {
      targetRotationSteps  = (long)(RS[0].as<float>() * ROTATION_STEPS_PER_DEG);
      targetElevationSteps = (long)(RS[1].as<float>() * ELEVATION_STEPS_PER_DEG);
      hasShoulder = true;
    }

    // Queue stepper targets (non-blocking — .run() advances below)
    if (hasShoulder) {
      shoulderRotation.moveTo(targetRotationSteps);
      shoulderElevation.moveTo(targetElevationSteps);
    }

    // Initialize current servo positions from previous keyframe
    int currentHand[HAND_SERVO_COUNT];
    int currentWrist[WRIST_SERVO_COUNT];
    int currentElbow[ELBOW_SERVO_COUNT];

    static int prevHand[HAND_SERVO_COUNT]   = {90, 90, 90, 90, 90};
    static int prevWrist[WRIST_SERVO_COUNT] = {90, 90};
    static int prevElbow[ELBOW_SERVO_COUNT] = {90};

    if (hasHand)  { for (int i = 0; i < HAND_SERVO_COUNT;  i++) currentHand[i]  = prevHand[i]; }
    if (hasWrist) { for (int i = 0; i < WRIST_SERVO_COUNT; i++) currentWrist[i] = prevWrist[i]; }
    if (hasElbow) { for (int i = 0; i < ELBOW_SERVO_COUNT; i++) currentElbow[i] = prevElbow[i]; }

    // Find max servo steps needed
    int maxSteps = 0;
    if (hasHand)  { for (int i = 0; i < HAND_SERVO_COUNT;  i++) { int s = abs(targetHandAngles[i]  - currentHand[i]);  if (s > maxSteps) maxSteps = s; } }
    if (hasWrist) { for (int i = 0; i < WRIST_SERVO_COUNT; i++) { int s = abs(targetWristAngles[i] - currentWrist[i]); if (s > maxSteps) maxSteps = s; } }
    if (hasElbow) { for (int i = 0; i < ELBOW_SERVO_COUNT; i++) { int s = abs(targetElbowAngles[i] - currentElbow[i]); if (s > maxSteps) maxSteps = s; } }

    // Move all servos concurrently, advance steppers each iteration
    for (int step = 0; step < maxSteps; step++) {
      if (hasHand) {
        for (int i = 0; i < HAND_SERVO_COUNT; i++) {
          if (currentHand[i] != targetHandAngles[i])
            currentHand[i] += (currentHand[i] < targetHandAngles[i]) ? 1 : -1;
          handServos[i].write(currentHand[i]);
        }
      }
      if (hasWrist) {
        for (int i = 0; i < WRIST_SERVO_COUNT; i++) {
          if (currentWrist[i] != targetWristAngles[i])
            currentWrist[i] += (currentWrist[i] < targetWristAngles[i]) ? 1 : -1;
          wristServos[i].write(currentWrist[i]);
        }
      }
      if (hasElbow) {
        for (int i = 0; i < ELBOW_SERVO_COUNT; i++) {
          if (currentElbow[i] != targetElbowAngles[i])
            currentElbow[i] += (currentElbow[i] < targetElbowAngles[i]) ? 1 : -1;
          elbowServos[i].write(currentElbow[i]);
        }
      }

      // Advance steppers alongside servos (non-blocking)
      shoulderRotation.run();
      shoulderElevation.run();

      delay(DEFAULT_STEP_DELAY);
    }

    // Update previous servo positions
    if (hasHand)  { for (int i = 0; i < HAND_SERVO_COUNT;  i++) prevHand[i]  = targetHandAngles[i]; }
    if (hasWrist) { for (int i = 0; i < WRIST_SERVO_COUNT; i++) prevWrist[i] = targetWristAngles[i]; }
    if (hasElbow) { for (int i = 0; i < ELBOW_SERVO_COUNT; i++) prevElbow[i] = targetElbowAngles[i]; }

    // Finish any remaining stepper movement after servo loop completes
    while (shoulderRotation.distanceToGo() != 0 || shoulderElevation.distanceToGo() != 0) {
      shoulderRotation.run();
      shoulderElevation.run();
    }

    // Update previous stepper positions
    if (hasShoulder) {
      prevRotationSteps  = targetRotationSteps;
      prevElevationSteps = targetElevationSteps;
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

  Serial.println("[RIGHT_ARM] Booting...");

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

  // Configure shoulder stepper pins
  pinMode(shoulder1_stepPin,   OUTPUT);
  pinMode(shoulder1_dirPin,    OUTPUT);
  pinMode(shoulder1_enablePin, OUTPUT);
  pinMode(shoulder1_ms1Pin,    OUTPUT);
  pinMode(shoulder1_ms2Pin,    OUTPUT);
  pinMode(shoulder2_stepPin,   OUTPUT);
  pinMode(shoulder2_dirPin,    OUTPUT);
  pinMode(shoulder2_enablePin, OUTPUT);
  pinMode(shoulder2_ms1Pin,    OUTPUT);
  pinMode(shoulder2_ms2Pin,    OUTPUT);

  // 1/16 microstepping: MS1=HIGH, MS2=HIGH on A4988
  digitalWrite(shoulder1_ms1Pin, HIGH);
  digitalWrite(shoulder1_ms2Pin, HIGH);
  digitalWrite(shoulder2_ms1Pin, HIGH);
  digitalWrite(shoulder2_ms2Pin, HIGH);

  // Enable motors (ENABLE is active LOW)
  digitalWrite(shoulder1_enablePin, LOW);
  digitalWrite(shoulder2_enablePin, LOW);

  // Configure AccelStepper
  shoulderRotation.setMaxSpeed(SHOULDER_MAX_SPEED);
  shoulderRotation.setAcceleration(SHOULDER_ACCEL);
  shoulderElevation.setMaxSpeed(SHOULDER_MAX_SPEED);
  shoulderElevation.setAcceleration(SHOULDER_ACCEL);

  Serial.println("[RIGHT_ARM] Ready for motion commands.");
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
