# ASL Robot

An ASL (American Sign Language) robot that converts spoken English into ASL signs using real-time speech recognition, AI translation, and dual robotic arm execution.

## System Architecture

The system uses a **multi-threaded pipeline** with four worker threads coordinated through a centralized `FileIOManager`:

```
Microphone → STT → English Text → Gemini AI → ASL Tokens → MongoDB → Motion Scripts → ESP32s → Servos
```

1. **STT Thread** (`stt_io.py`) — Listens for speech, detects wake words, streams transcribed text
2. **AI Thread** (`ai_io.py`) — Translates English to ASL gloss tokens via Gemini AI
3. **DB Thread** (`db_io.py`) — Looks up sign motion data from MongoDB
4. **Motion Thread** (`motion_io.py`) — Sends motion scripts to ESP32 boards over serial

## Project Structure

```
ASL-Robot/
├── src/
│   ├── main.py                     # System entry point
│   ├── config/
│   │   └── settings.py             # Environment variable loading
│   ├── database/
│   │   ├── db_connection.py        # MongoDB connection
│   │   └── db_functions.py         # MongoDB queries
│   ├── speech_to_text/
│   │   └── stt.py                  # Google Cloud STT
│   ├── text_to_ASL/
│   │   └── translate_AI.py         # Gemini AI translation
│   ├── io/
│   │   ├── fileIO.py               # FileIOManager (thread coordination)
│   │   ├── stt_io.py               # STT thread
│   │   ├── ai_io.py                # AI translation thread
│   │   ├── db_io.py                # Database lookup thread
│   │   └── motion_io.py            # Serial motion thread
│   ├── signs/
│   │   ├── signs_to_seed.json      # Sign definitions (187 signs)
│   │   └── seed_signs.py           # MongoDB seeder script
│   ├── microcontrollers/
│   │   ├── platformio.ini          # PlatformIO config (2 ESP32 targets)
│   │   └── src/
│   │       ├── left_arm.cpp        # Left arm firmware
│   │       └── right_arm.cpp       # Right arm firmware
│   └── fk_tool/                    # Forward kinematics evaluation tool
│       ├── cli.py                  # CLI (evaluate, visualize, compare)
│       ├── fk_engine.py            # 5-DOF FK engine (numpy)
│       ├── servo_mapper.py         # Servo ↔ joint angle conversion
│       ├── sign_parser.py          # Sign JSON parser with hold-forward
│       ├── evaluator.py            # 6-check sign evaluator
│       ├── visualizer.py           # 3D matplotlib visualization
│       ├── loaders.py              # JSON, MongoDB, AI output loaders
│       ├── report.py               # Console, CSV, HTML reporting
│       ├── config.py               # Robot dimensions and calibration
│       ├── models.py               # Data models
│       └── tests/                  # Test suite (22 tests)
├── docs/                           # Guides and design documents
├── eval/                           # Evaluation outputs (reports, animations)
├── requirements.txt                # Python dependencies
└── .env                            # Environment variables (not tracked)
```

## Hardware

- **2x ESP32** dev boards (left arm + right arm)
- **16 servos + 4 stepper motors** per robot (8 servos + 2 steppers per arm):
  - Hands (`L`/`R`): 5 servos each — finger articulation
  - Wrists (`LW`/`RW`): 2 servos each — flexion and pronation
  - Elbows (`LE`/`RE`): 1 servo each — flexion/extension
  - Shoulders (`LS`/`RS`): 2 **stepper motors** each (A4988 drivers) — rotation and flexion/elevation. The JSON schema still represents these as 0–180° "servo angle" arrays; firmware converts to steps via `ROTATION_STEPS_PER_DEG` / `ELEVATION_STEPS_PER_DEG` and homes each axis against a limit switch at boot.
- Serial communication at 115200 baud (default: `COM3` left, `COM4` right)
- JSON command protocol, 3-command queue, smooth interpolated motion

## Setup

### 1. Python Dependencies

Requires Python 3.10+.

```bash
pip install -r requirements.txt
```

### 2. Environment Variables

Create a `.env` file in the project root:

```
MONGODB_URI=mongodb+srv://<USERNAME>:<PASSWORD>@<YOUR_CLUSTER>.mongodb.net/
MONGODB_DB_NAME=ASLSignsDB
GOOGLE_APPLICATION_CREDENTIALS="stt_key_file.json"
GEMINI_API_KEY="your-gemini-api-key-here"
```

For **`python -m src.testing.sign_demo`** only, the sign demo module enables minimal validation: **`MONGODB_URI`** and **`MONGODB_DB_NAME`** are sufficient (no Google STT or Gemini). The full app (`src.main`) still requires all variables above.

### 3. Google Cloud STT Credentials

Place your Google Cloud service account JSON key file in the project root as `stt_key_file.json`. This is referenced by the `GOOGLE_APPLICATION_CREDENTIALS` env var. Ensure both `stt_key_file.json` and `.env` are in `.gitignore`.

### 4. Seed the Database

```bash
python -m src.signs.seed_signs
```

### 5. Flash ESP32 Firmware

```bash
cd src/microcontrollers
pio run -e left_arm -t upload    # Flash left arm
pio run -e right_arm -t upload   # Flash right arm
```

Dependencies (installed automatically by PlatformIO): ESP32Servo, ArduinoJson, AccelStepper.

## Running

```bash
python -B -m src.main
```

- Say a wake phrase ("fred", "hey fred", "frederick") to activate
- Speak your sentence — the robot translates and signs it
- Say "fred stop" or "thank you fred" to deactivate
- **Ctrl+C** exits cleanly (threads stop, serial ports close)

## Sign demo (modular testing)

Run signs directly from the terminal without speech, AI translation, or the emotion UI. Only MongoDB resolution and the motion serial thread start — no STT, no T5/Whisper, no Gemini.

```bash
python -B -m src.testing.sign_demo
```

- Each input line is split on whitespace and every token is queued in order. `HELLO` runs one sign; `HELLO FRIEND` chains two; unknown tokens fall back to character-by-character fingerspelling.
- Token lookup is **case-insensitive** — `hello`, `Hello`, and `HELLO` all resolve to the same MongoDB document.
- **Bilateral signs** (keyframes containing both `L*` and `R*` keys) are routed to both ESP32s automatically.
- **`--dry-run`** prints motion JSON only (no serial connection, no motion thread).
- Serial ports: **`--left-port`** / **`--right-port`**, or env **`ASL_LEFT_PORT`** / **`ASL_RIGHT_PORT`** (defaults match `motion_io`: `COM3`, `COM4`).

Examples:

```bash
python -B -m src.testing.sign_demo
python -B -m src.testing.sign_demo --dry-run
python -B -m src.testing.sign_demo --left-port COM3 --right-port COM5
```

Interactive commands: `help`, `quit` / `exit` / `q`.

## Forward Kinematics Tool

A standalone evaluation and visualization tool that ports Professor LaMack's MATLAB `PlotRobotLinks` to Python. It validates sign data, renders 3D arm poses, and compares AI-generated signs against reference data.

**5-DOF kinematic chain per arm:** shoulder swing (q1) → shoulder abduction (q2) → elbow flexion (q3) → wrist flexion (q4) → wrist pronation (q5), using 4x4 homogeneous transformation matrices.

### Usage

```bash
# Evaluate all signs from a JSON file
python -m src.fk_tool evaluate --input src/signs/signs_to_seed.json

# Evaluate signs from MongoDB
python -m src.fk_tool evaluate --source mongodb

# Evaluate specific signs with HTML report
python -m src.fk_tool evaluate --source mongodb --tokens HELLO THANK_YOU --report eval/report.html

# Visualize a sign (static first keyframe)
python -m src.fk_tool visualize --input src/signs/signs_to_seed.json --token HELLO

# Animate a sign
python -m src.fk_tool visualize --input src/signs/signs_to_seed.json --token HELLO --animate

# Compare AI output against reference signs
python -m src.fk_tool compare --ai-input ai_signs.json --ref-source mongodb --report eval/comparison.html
```

### Evaluation Checks

| Check | Description |
|-------|-------------|
| Servo range | All servo values within 0-180° |
| Joint limits | Joint angles within mechanical limits |
| Timing | Keyframe times monotonic and within duration |
| Angular velocity | No servo movement exceeds 500°/s |
| Duration | Sign duration between 0.3s and 5.0s |
| Completeness | All required servo groups present |

## Sign Data Schema

```json
{
  "token": "HELLO",
  "type": "DYNAMIC",
  "duration": 2.0,
  "keyframes": [
    {
      "time": 0.0,
      "L": [180, 0, 0, 0, 0],
      "R": [0, 0, 0, 0, 0],
      "LW": [90, 90],
      "RW": [90, 90],
      "LE": [90],
      "RE": [90],
      "LS": [90, 90],
      "RS": [90, 90]
    }
  ]
}
```

- **token**: ASL gloss token (uppercase)
- **type**: `STATIC` (single pose) or `DYNAMIC` (animated keyframes)
- **duration**: Total sign duration in seconds
- **Servo groups**: All optional per keyframe — omitted groups hold their previous position

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Serial connection fails | Check COM port in `motion_io.py` (defaults `COM3` / `COM4`), verify both ESP32s are connected, confirm 115200 baud |
| Shoulders don't move / hit limits at boot | Steppers home against limit switches on startup — power on with arms in a homing-safe pose. Confirm A4988 enable/dir/step pins match `*_arm.cpp` |
| Database connection fails | Verify `MONGODB_URI` and `MONGODB_DB_NAME` in `.env` |
| Speech recognition fails | Check `stt_key_file.json` exists, verify mic permissions, ensure Cloud STT API is enabled |
| AI translation fails | Verify `GEMINI_API_KEY` in `.env` |
