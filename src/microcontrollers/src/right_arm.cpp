#include <Arduino.h>
#include <ESP32Servo.h>
#include <ArduinoJson.h>
#include <AccelStepper.h>
#include <Preferences.h>

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

// Elbow slowdown factor — elbow advances 1 step every N outer iterations.
// Higher = slower/smoother elbow; hand & wrist are unaffected.
#define ELBOW_SLOWDOWN     3

// Stepper calibration (both arms share same hardware, so same constants)
// Rotation axis — tune for actual gear ratio
#define ROTATION_STEPS_PER_DEG  320.0f
// Elevation axis — 25:1 gearbox
#define ELEVATION_STEPS_PER_DEG 222.22f  // 3200 * 25 / 360

#define SHOULDER_MAX_SPEED 10000.0f
#define SHOULDER_ACCEL     5000.0f

// Shoulder joint limits (degrees)
#define ROTATION_MIN_DEG    0.0f
#define ROTATION_MAX_DEG    180.0f
#define ELEVATION_MIN_DEG   0.0f
#define ELEVATION_MAX_DEG   180.0f

// Converted to step limits
#define ROTATION_MIN_STEPS  ((long)(ROTATION_MIN_DEG  * ROTATION_STEPS_PER_DEG))
#define ROTATION_MAX_STEPS  ((long)(ROTATION_MAX_DEG  * ROTATION_STEPS_PER_DEG))
#define ELEVATION_MIN_STEPS ((long)(ELEVATION_MIN_DEG * ELEVATION_STEPS_PER_DEG))
#define ELEVATION_MAX_STEPS ((long)(ELEVATION_MAX_DEG * ELEVATION_STEPS_PER_DEG))

// Homing configuration
#define HOMING_ENABLED       false   // Set true when limit switches are installed
#define HOMING_SPEED         2000.0f
#define HOMING_BACKOFF_STEPS 200

// Per-axis homing direction (+1 or -1). Flip the sign for an axis whose motor
// moves AWAY from its limit switch when stepping negative.
#define ROTATION_HOME_DIR    -1
#define ELEVATION_HOME_DIR   -1

// Return-to-start-pose after each sign
#define RETURN_TO_START_POSE true

// ================================
// SERVO DECLARATIONS
// ================================
Servo handServos[HAND_SERVO_COUNT];
Servo wristServos[WRIST_SERVO_COUNT];
Servo elbowServos[ELBOW_SERVO_COUNT];

// Hand servos (R): Thumb, Index, Middle, Ring, Pinky
int handPins[HAND_SERVO_COUNT]   = {2, 4, 5, 18, 19};
// Wrist servos (RW): Rotation, Flexion/Extension
int wristPins[WRIST_SERVO_COUNT] = {21, 22};
// Elbow servo (RE)
int elbowPins[ELBOW_SERVO_COUNT] = {23};

// ================================
// SHOULDER STEPPER PINS
// ================================
// Motor 1: Shoulder Rotation (internal/external rotation) — 36:1 gearbox
const int shoulder1_stepPin   = 33;
const int shoulder1_dirPin    = 32;
const int shoulder1_enablePin = 25;

// Motor 2: Shoulder Flexion/Elevation (raise/lower) — 25:1 gearbox
const int shoulder2_stepPin   = 27;
const int shoulder2_dirPin    = 26;
const int shoulder2_enablePin = 14;

// Limit switch pins (active LOW with INPUT_PULLUP)
const int rotationLimitPin  = 34;
const int elevationLimitPin = 35;

// ================================
// SHOULDER STEPPER OBJECTS
// AccelStepper::DRIVER = STEP + DIR interface (MS1/MS2 hardwired on driver board)
// ================================
AccelStepper shoulderRotation(AccelStepper::DRIVER, shoulder1_stepPin, shoulder1_dirPin);
AccelStepper shoulderFlexion(AccelStepper::DRIVER,  shoulder2_stepPin, shoulder2_dirPin);

// ================================
// PER-JOINT STATE
// ================================
struct JointState {
  long current_steps;
  long min_steps;
  long max_steps;
  long home_offset_steps;
};

JointState rotationState  = {0, ROTATION_MIN_STEPS,  ROTATION_MAX_STEPS,  0};
JointState elevationState = {0, ELEVATION_MIN_STEPS, ELEVATION_MAX_STEPS, 0};

// NVS persistence
Preferences prefs;

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
// HELPERS: CLAMPING, NVS, HOMING
// ================================
long clampSteps(long target, const JointState &state) {
  if (target < state.min_steps) return state.min_steps;
  if (target > state.max_steps) return state.max_steps;
  return target;
}

void savePositionNVS() {
  prefs.begin("shoulder", false);
  prefs.putLong("rot_steps", rotationState.current_steps);
  prefs.putLong("elev_steps", elevationState.current_steps);
  prefs.end();
}

void loadPositionNVS() {
  prefs.begin("shoulder", true);
  rotationState.current_steps  = prefs.getLong("rot_steps", 0);
  elevationState.current_steps = prefs.getLong("elev_steps", 0);
  prefs.end();
}

void homeAxis(AccelStepper &stepper, int limitPin, JointState &state, int homeDir) {
  if (!HOMING_ENABLED) return;

  pinMode(limitPin, INPUT_PULLUP);
  Serial.print("[RIGHT_ARM] Homing axis...");

  stepper.setMaxSpeed(HOMING_SPEED);
  stepper.moveTo((long)homeDir * 999999);

  while (digitalRead(limitPin) == HIGH) {
    stepper.run();
    yield();
  }

  stepper.stop();
  stepper.setCurrentPosition(state.home_offset_steps);
  state.current_steps = state.home_offset_steps;

  // Back off from switch (opposite of homing direction)
  stepper.moveTo(state.home_offset_steps - (long)homeDir * HOMING_BACKOFF_STEPS);
  while (stepper.distanceToGo() != 0) {
    stepper.run();
    yield();
  }
  state.current_steps = stepper.currentPosition();

  stepper.setMaxSpeed(SHOULDER_MAX_SPEED);
  Serial.println(" done.");
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

  // Capture start pose for return-to-start after sign
  long startRotationSteps  = rotationState.current_steps;
  long startElevationSteps = elevationState.current_steps;

  // Process each keyframe
  for (JsonObject frame : keyframes) {

    // Extract target servo angles
    int targetHandAngles[HAND_SERVO_COUNT];
    int targetWristAngles[WRIST_SERVO_COUNT];
    int targetElbowAngles[ELBOW_SERVO_COUNT];

    bool hasHand = false, hasWrist = false, hasElbow = false, hasShoulder = false;

    // Stepper targets default to current position (no movement if RS absent)
    long targetRotationSteps  = rotationState.current_steps;
    long targetElevationSteps = elevationState.current_steps;

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
      targetRotationSteps  = (long)((RS[0].as<float>() - 90.0f) * ROTATION_STEPS_PER_DEG);
      targetElevationSteps = (long)((RS[1].as<float>() - 90.0f) * ELEVATION_STEPS_PER_DEG);
      hasShoulder = true;
    }

    // Clamp stepper targets to joint limits
    targetRotationSteps  = clampSteps(targetRotationSteps,  rotationState);
    targetElevationSteps = clampSteps(targetElevationSteps, elevationState);

    // Queue stepper targets (non-blocking — .run() advances below)
    if (hasShoulder) {
      shoulderRotation.moveTo(targetRotationSteps);
      shoulderFlexion.moveTo(targetElevationSteps);
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
    if (hasElbow) { for (int i = 0; i < ELBOW_SERVO_COUNT; i++) { int s = abs(targetElbowAngles[i] - currentElbow[i]) * ELBOW_SLOWDOWN; if (s > maxSteps) maxSteps = s; } }

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
      if (hasElbow && (step % ELBOW_SLOWDOWN == 0)) {
        for (int i = 0; i < ELBOW_SERVO_COUNT; i++) {
          if (currentElbow[i] != targetElbowAngles[i])
            currentElbow[i] += (currentElbow[i] < targetElbowAngles[i]) ? 1 : -1;
          elbowServos[i].write(currentElbow[i]);
        }
      }

      // Advance steppers alongside servos (non-blocking)
      shoulderRotation.run();
      shoulderFlexion.run();

      delay(DEFAULT_STEP_DELAY);
    }

    // Update previous servo positions
    if (hasHand)  { for (int i = 0; i < HAND_SERVO_COUNT;  i++) prevHand[i]  = targetHandAngles[i]; }
    if (hasWrist) { for (int i = 0; i < WRIST_SERVO_COUNT; i++) prevWrist[i] = targetWristAngles[i]; }
    if (hasElbow) { for (int i = 0; i < ELBOW_SERVO_COUNT; i++) prevElbow[i] = targetElbowAngles[i]; }

    // Finish any remaining stepper movement after servo loop completes
    while (shoulderRotation.distanceToGo() != 0 || shoulderFlexion.distanceToGo() != 0) {
      shoulderRotation.run();
      shoulderFlexion.run();
    }

    // Update joint state
    if (hasShoulder) {
      rotationState.current_steps  = targetRotationSteps;
      elevationState.current_steps = targetElevationSteps;
    }

    // Calculate frame time based on duration
    float frameTime = duration / frameCount;
    delay((int)(frameTime * 1000));
  }

  // Return to start pose after sign execution
  if (RETURN_TO_START_POSE) {
    shoulderRotation.moveTo(startRotationSteps);
    shoulderFlexion.moveTo(startElevationSteps);
    while (shoulderRotation.distanceToGo() != 0 || shoulderFlexion.distanceToGo() != 0) {
      shoulderRotation.run();
      shoulderFlexion.run();
    }
    rotationState.current_steps  = startRotationSteps;
    elevationState.current_steps = startElevationSteps;
  }

  // Persist position to NVS
  savePositionNVS();

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

  // Shoulder stepper 1 (Rotation)
  pinMode(shoulder1_stepPin,   OUTPUT);
  pinMode(shoulder1_dirPin,    OUTPUT);
  pinMode(shoulder1_enablePin, OUTPUT);
  digitalWrite(shoulder1_enablePin, LOW);  // active LOW

  // Shoulder stepper 2 (Flexion/Elevation)
  pinMode(shoulder2_stepPin,   OUTPUT);
  pinMode(shoulder2_dirPin,    OUTPUT);
  pinMode(shoulder2_enablePin, OUTPUT);
  digitalWrite(shoulder2_enablePin, LOW);  // active LOW

  // AccelStepper config
  shoulderRotation.setMaxSpeed(SHOULDER_MAX_SPEED);
  shoulderRotation.setAcceleration(SHOULDER_ACCEL);
  shoulderFlexion.setMaxSpeed(SHOULDER_MAX_SPEED);
  shoulderFlexion.setAcceleration(SHOULDER_ACCEL);

  // Load last-known position from NVS (fallback before homing)
  loadPositionNVS();
  shoulderRotation.setCurrentPosition(rotationState.current_steps);
  shoulderFlexion.setCurrentPosition(elevationState.current_steps);
  Serial.print("[RIGHT_ARM] NVS loaded — rot:");
  Serial.print(rotationState.current_steps);
  Serial.print(" elev:");
  Serial.println(elevationState.current_steps);

  // Home both axes (no-op if HOMING_ENABLED is false)
  homeAxis(shoulderRotation, rotationLimitPin,  rotationState,  ROTATION_HOME_DIR);
  homeAxis(shoulderFlexion,  elevationLimitPin, elevationState, ELEVATION_HOME_DIR);

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
