# Project Context: ASL Robot

This document provides a comprehensive technical overview of the ASL (American Sign Language) Robot project, including its architecture, core components, data flow, key data structures, and recent improvements.

---

## 1. Project Overview

The ASL Robot is a system designed to convert spoken English into American Sign Language (ASL) gestures performed by a dual-arm robotic platform. It operates in real-time by capturing audio from a microphone, processing it through a multi-stage pipeline, and ultimately generating physical movements in the robot. The system is architected to be modular and extensible, allowing individual components like speech recognition or AI translation to be updated or replaced with minimal impact on the rest of the system.

---

## 2. System Architecture

The application is built on a **multi-threaded pipeline architecture**. Four main components (STT, AI, Database, and Motion) operate concurrently as separate threads. They communicate in a decoupled manner through a central `FileIOManager` object, which uses thread-safe queues to pass data between them. This design allows for parallel processing; for example, the AI can be translating a sentence while the robot is already signing a previously translated one.

### Key Files

-   **`src/main.py`**: The main entry point of the system. It is responsible for instantiating the `FileIOManager` and initializing and starting the four primary worker threads as daemons.
-   **`src/io/fileIO.py`**: Contains the `FileIOManager` class. This crucial class acts as the central message bus, managing a set of `Queue` objects that buffer data between the threads, preventing any single process from blocking another.

### Data Flow

The data processing pipeline proceeds as follows:

1.  **Audio Input**: The STT thread captures raw audio from a microphone.
2.  **Speech-to-Text**: This audio is streamed to a speech recognition service (cloud or local), which transcribes it into English text.
3.  **Text-to-ASL Gloss**: The transcribed text is passed to a translation model, which converts it into ASL gloss—a textual representation of signs.
4.  **Gloss-to-Motion Script**: The ASL gloss tokens are used to look up detailed motion scripts from a database.
5.  **Motion Execution**: The motion scripts, which are JSON objects containing servo commands, are sent via serial communication to microcontroller-driven robot arms.

```
[Microphone] → STT Thread → [English Text] → AI Thread → [ASL Tokens] → DB Thread → [Motion Scripts] → Motion Thread → [Serial Commands] → [Arduino Controllers] → [Servo Motors]
```

---

## 3. Core Modules & Components

### a. Speech-to-Text (STT)

**Key Files**: 
- `src/speech_to_text/base_stt.py` - Abstract base class
- `src/speech_to_text/cloud_stt.py` - Google Cloud implementation
- `src/speech_to_text/local_stt.py` - Whisper local implementation
- `src/speech_to_text/stt_factory.py` - Factory pattern for engine selection
- `src/io/stt_io.py` - STT thread coordinator

**Dependencies**: `google-cloud-speech`, `pyaudio`, `openai-whisper`, `torch`, `torchaudio`

**Implementation**: This module provides dual-mode speech recognition:

#### Cloud STT (Google Cloud Speech-to-Text)
- Streaming real-time transcription via Google Cloud API
- Requires internet connection and API credentials
- Excellent accuracy for general speech
- Higher latency due to network round-trip

#### Local STT (OpenAI Whisper)
- Runs entirely offline on local hardware
- Uses OpenAI's Whisper model (configurable size: tiny, base, small, medium, large)
- No API costs, fully private
- Lower latency (no network delay)
- One-time model download (~150MB for 'base')

**Configuration**: The active engine is selected via `.env`:
```bash
STT_ENGINE=cloud  # or 'local'
LOCAL_STT_MODEL=base  # Whisper model size (if using local)
LOCAL_STT_DEVICE=cpu  # 'cpu' or 'cuda' (if using local)
```

**Functionality**: 
- Wake-word detection mechanism listens for phrases like "Hey Fred", "Frederick", "Freddy"
- Stop-phrases like "Fred stop", "Stop moving" terminate the translation session
- Final transcripts are placed into a queue managed by `FileIOManager`
- Both engines use the same interface and support identical wake word detection

---

### b. Text-to-ASL (AI Translation)

**Key File**: `src/text_to_ASL/translate_AI.py`

**Dependencies**: `torch`, `transformers`

**Implementation**: This module utilizes a pre-trained model from the Hugging Face Hub: **`AchrafAzzaouiRiceU/t5-english-to-asl-gloss`**. This is a T5-based model specifically fine-tuned for translating English text to ASL gloss.

**Functionality**: 
- The AI thread continuously polls for new English sentences from its input queue
- When text is available, it formats it into a prompt and generates ASL gloss using the loaded model
- Performs post-processing: converting to uppercase, removing unnecessary words, moving question words (WHO, WHAT, etc.) to the end of the sentence (grammatically correct in ASL)
- Places the resulting list of gloss tokens into the next queue

---

### c. Database (DB)

**Key Files**: 
- `src/database/db_connection.py` - MongoDB connection initialization
- `src/database/db_functions.py` - MongoDB database functions/interactions
- `src/io/db_io.py` - Database I/O thread
- `src/signs/seed_signs.py` - Database seeder script
- `src/signs/signs_to_seed.json` - Sign data source

**Dependencies**: `pymongo`

**Implementation**: The system uses **MongoDB** as its database for storing sign motion data. The `db_io.py` thread handles the logic of retrieving signs.

**Functionality**: 
- This thread polls for ASL gloss tokens from the AI's output queue
- When a token is available, it queries the MongoDB collection to find the corresponding document
- The document contains the full motion script required to perform the sign
- **Fallback**: If a token is not found in the database, the system automatically triggers fingerspelling, breaking the word into individual letters and queuing each letter's motion
- Retrieved scripts are then enqueued for the Motion thread

---

### d. Motion Control

**Key Files**: 
- `src/io/motion_io.py` - Motion I/O thread with ACK synchronization
- `src/microcontrollers/src/left_arm.cpp` - Left arm Arduino controller
- `src/microcontrollers/src/right_arm.cpp` - Right arm Arduino controller

**Dependencies**: `pyserial`

**Implementation**: The `motion_io.py` thread is the bridge between the software and the physical hardware. It establishes and manages serial connections to two separate Arduino controllers (one for each arm, using ports like `COM3` and `COM6`).

**Recent improvements (Sprint 5–6)**:

#### ACK-Based Synchronization
- Python waits for Arduino to send "ACK" message before sending next command
- Prevents queue overflow on Arduino (3-command buffer)
- Reduces unnecessary latency (no fixed sleep delays)
- Separate ACK tracking for left and right arms
- 8-second timeout prevents indefinite blocking

#### Smart Delays for Fingerspelling
- **Fingerspelling delay**: 30ms between letters (smooth, fast flow)
- **Sign delay**: 150ms between full signs (natural pacing)
- Automatically detected: single-character token = fingerspelling
- Configurable via constants: `FINGERSPELL_POST_DELAY`, `SIGN_POST_DELAY`

#### Intelligent Command Routing
- Inspects keyframes to determine which arm(s) need each command
- Left-only signs → sent only to left controller
- Right-only signs → sent only to right controller  
- Two-handed signs → sent to both controllers
- 50% reduction in serial traffic for single-arm motions

**Sprint 6**: Graceful shutdown on Ctrl+C (shutdown event, serial cleanup); rest position for inactive arm when switching context; keyframes always sent as array for Arduino compatibility; motion I/O refactored with shared send helper and general code cleanup.

**Functionality**: 
- Polls for motion scripts from the database output queue
- Routes commands intelligently to appropriate controller(s)
- Serializes JSON objects and sends over serial port
- Waits for ACK before sending next command to each arm
- Includes error handling to detect disconnected controllers and attempts to reconnect periodically
- The C++ code in `src/microcontrollers/src/` uses the `ArduinoJson` library to parse commands and `VarSpeedServo` to execute smooth servo movements

---

## 4. Hardware and Firmware

**Microcontrollers**: The robot arms are controlled by two **Arduino** boards (or ESP32 boards).

**Firmware**: The code for the microcontrollers is written in C++ using the Arduino framework and is managed by PlatformIO.

**Key Files**: 
- `src/microcontrollers/src/left_arm.cpp`
- `src/microcontrollers/src/right_arm.cpp`
- `platformio.ini` - PlatformIO configuration for both arms

**Libraries**:
- `ArduinoJson`: Used to parse JSON motion scripts received over serial
- `VarSpeedServo` / `ESP32Servo`: Controls multiple servos with variable speed for smooth, natural movements

**Communication Protocol**:
- Receives JSON motion scripts via serial (115200 baud)
- Parses keyframes and executes servo movements
- Sends "ACK" message when motion completes
- Command queue size: 3 commands maximum

---

## 5. Sign Data Schema

The core of the motion system is the data structure used to define each sign. This schema is used in the MongoDB documents and the JSON files.

### Fields

-   **`token`**: The unique identifier for the sign, corresponding to an ASL gloss word (e.g., "HELLO")
-   **`type`**: Defines the nature of the sign's motion
    -   **`STATIC`**: A sign that involves moving to a single position and holding it
    -   **`DYNAMIC`**: A sign composed of a sequence of movements through multiple keyframes
-   **`duration`**: The total time in seconds that the sign should take to complete
-   **`keyframes`**: An array or dictionary of objects, where each object represents a snapshot of the robot's servo positions at a specific time
    -   **`time`**: A timestamp in seconds, relative to the start of the sign (from `0.0` to `duration`)
    -   **Servo Groups**: A keyframe contains one or more servo groups, each an array of integer angles (0-180°)
        -   `L`: Left Hand (5 servos) - finger and hand articulation
        -   `R`: Right Hand (5 servos) - finger and hand articulation
        -   `LW`: Left Wrist (2 servos) - wrist rotation and flexion
        -   `RW`: Right Wrist (2 servos) - wrist rotation and flexion
        -   `LE`: Left Elbow (1 servo) - elbow flexion/extension
        -   `RE`: Right Elbow (1 servo) - elbow flexion/extension
        -   `LS`: Left Shoulder (2 servos) - shoulder rotation and elevation
        -   `RS`: Right Shoulder (2 servos) - shoulder rotation and elevation

### Example Schema

```json
{
  "token": "HELLO",
  "type": "DYNAMIC",
  "duration": 2.0,
  "keyframes": [
    {
      "time": 0.0,
      "L": [180, 0, 0, 0, 0],
      "LW": [90, 90]
    },
    {
      "time": 1.0,
      "L": [180, 20, 20, 20, 20]
    },
    {
      "time": 2.0,
      "L": [180, 0, 0, 0, 0],
      "LW": [90, 90]
    }
  ]
}
```

**Note**: Not all servo groups need to be present in every keyframe. If a servo group is omitted from a keyframe, its servos will maintain their positions from the previous keyframe. The routing system inspects these keys to determine which controller(s) need each command.

---

## 6. Setup and Configuration

### a. Environment Configuration

Create a `.env` file in the project root with the following variables:

```bash
# ============================================
# Database Configuration
# ============================================
MONGODB_URI=mongodb+srv://<USERNAME>:<PASSWORD>@<YOUR_CLUSTER>.mongodb.net/
MONGODB_DB_NAME=ASLSignsDB

# ============================================
# Speech-to-Text Configuration
# ============================================
# STT Engine Selection: 'cloud' or 'local'
STT_ENGINE=cloud

# Cloud STT Configuration (only used when STT_ENGINE=cloud)
GOOGLE_APPLICATION_CREDENTIALS="stt_key_file.json"

# Local STT Configuration (only used when STT_ENGINE=local)
# Model options: 'tiny', 'base', 'small', 'medium', 'large'
LOCAL_STT_MODEL=base
LOCAL_STT_DEVICE=cpu  # 'cpu' or 'cuda'

# ============================================
# AI Translation Configuration
# ============================================
GEMINI_API_KEY="your-gemini-api-key-here"
```

### b. Dependencies Installation

**Python Dependencies**:
```bash
pip install -r requirements.txt
```

This installs:
- `pymongo` - MongoDB client
- `python-dotenv` - Environment variable loader
- `google-cloud-speech` - Google Cloud STT API client (cloud mode)
- `google-auth` - Google authentication library
- `pyaudio` - Audio input/output
- `google-genai` - Gemini AI API client
- `pyserial` - Serial communication with Arduino
- `openai-whisper` - Local STT engine (local mode)
- `torch`, `torchaudio` - PyTorch for Whisper
- `transformers` - Hugging Face transformers for AI translation

**Arduino Firmware**:
```bash
# Install PlatformIO
pip install platformio

# Upload firmware to each controller
pio run -e left_arm -t upload   # Left arm
pio run -e right_arm -t upload  # Right arm
```

### c. Database Seeding

Populate MongoDB with sign definitions:
```bash
python -m src.signs.seed_signs
```

To reset the database:
```bash
python -c "from src.signs.seed_signs import seed_signs; seed_signs(reset=True)"
```

---

## 7. Running the System

### Start the Main Application

```bash
python -B -m src.main
```

The system will:
1. Initialize all four threads (STT, AI, DB, Motion)
2. Connect to Arduino controllers via serial
3. Start listening for wake words

### Usage

1. **Activate**: Say a wake phrase (e.g., "hey fred", "frederick")
2. **Speak**: Say your sentence clearly
3. **Observe**: The robot will translate and sign your words
4. **Deactivate**: Say "stop moving" or "fred stop"

### Wake Words
- Activate: "fred", "frederick", "freddy", "hey fred", "fred please translate"
- Deactivate: "stop moving", "fred stop", "thank you fred"

---

## 8. Testing

### Validation Script

Verify all Sprint 5 changes are properly implemented:
```bash
python -m src.testing.validate_sprint5
```

This checks:
- All new STT files exist
- Configuration is valid
- STT factory works
- Motion pipeline has new features
- Dependencies are installed

### STT Testing

Test individual STT engines:
```bash
# Test cloud STT
python -m src.testing.test_stt cloud

# Test local STT
python -m src.testing.test_stt local
```

---

## 9. Recent Improvements

### Sprint 5 – Motion Pipeline Enhancements

1. **ACK-Based Synchronization** - Eliminated fixed delays, prevents queue overflow
2. **Smart Fingerspelling Delays** - 30ms between letters, 150ms between signs
3. **Intelligent Command Routing** - Only sends commands to necessary arm(s)
4. **Generalized Fingerspelling Fallback** - Any unknown word automatically fingerspelled
5. **Dual-Mode STT** - Choice between cloud (Google) or local (Whisper) speech recognition

**Performance**: ~25% faster execution, ~43% faster fingerspelling, 50% reduction in serial traffic for single-arm motions, 100% elimination of buffer overflow issues.

### Sprint 6 – Stability, UX & Cleanup

1. **Graceful shutdown** – Ctrl+C exits cleanly: shutdown event signals worker threads (AI, DB, Motion), serial ports are closed, and the process exits without force-kill.
2. **Rest position** – When switching context (e.g. two-arm sign → fingerspelling with one arm), the inactive arm is sent a neutral rest pose so it no longer stays frozen in the previous sign.
3. **Keyframes compatibility** – Python normalizes `keyframes` to a JSON array before sending over serial so Arduino always receives an array (fixes dict vs. array mismatch from some DB paths).
4. **Code cleanup** – ACK/send logic in `motion_io.py` extracted into a shared helper; unused imports and dead code removed; debug prints reduced; readability improved.

---

## 10. Troubleshooting

### STT Issues

**Cloud STT not working:**
- Verify `GOOGLE_APPLICATION_CREDENTIALS` points to valid JSON file
- Check internet connection
- Ensure Google Cloud Speech-to-Text API is enabled

**Local STT not working:**
- First run downloads Whisper model (~150MB for 'base')
- Check `LOCAL_STT_MODEL` is valid (tiny, base, small, medium, large)
- Try smaller model if experiencing performance issues

### Motion Pipeline Issues

**ACK timeouts:**
- Check Arduino is connected and powered
- Verify correct COM ports in `motion_io.py`
- Ensure firmware is uploaded correctly

**Serial connection issues:**
- Verify baud rate is 115200
- Check that Arduino is not being used by another program
- Try unplugging/replugging Arduino

**Signs not executing:**
- Check database is seeded: `python -m src.signs.seed_signs`
- Verify MongoDB connection in `.env`
- Check logs for database lookup errors

---

## 11. Project Structure

```
ASL-Robot/
├── src/
│   ├── main.py                      # System entry point
│   ├── config/
│   │   └── settings.py              # Environment configuration
│   ├── database/
│   │   ├── db_connection.py         # MongoDB connection
│   │   └── db_functions.py          # Database operations
│   ├── speech_to_text/
│   │   ├── base_stt.py             # STT abstract base class
│   │   ├── cloud_stt.py            # Google Cloud STT
│   │   ├── local_stt.py            # Whisper local STT
│   │   └── stt_factory.py          # STT engine factory
│   ├── text_to_ASL/
│   │   └── translate_AI.py          # AI translation
│   ├── io/
│   │   ├── fileIO.py               # Central message bus
│   │   ├── stt_io.py               # STT thread
│   │   ├── ai_io.py                # AI thread
│   │   ├── db_io.py                # Database thread
│   │   └── motion_io.py            # Motion thread
│   ├── signs/
│   │   ├── signs_to_seed.json      # Sign definitions
│   │   └── seed_signs.py           # Database seeder
│   ├── microcontrollers/
│   │   └── src/
│   │       ├── left_arm.cpp        # Left arm firmware
│   │       └── right_arm.cpp       # Right arm firmware
│   └── testing/
│       ├── test_stt.py             # STT testing script
│       └── validate_sprint5.py     # Validation script
├── .env                            # Environment variables
├── requirements.txt                # Python dependencies
├── platformio.ini                  # PlatformIO configuration
└── README.md                       # Project documentation
```

---

## 12. FK Simulation & Evaluation Tool

### 12a. Overview

The FK (Forward Kinematics) tool is a Python module at `src/fk_tool/` that simulates and evaluates the robot's arm motion scripts before deploying them to hardware. It is a direct port of Professor LaMack's MATLAB `PlotRobLinks` forward kinematics script into a full-featured, batch-capable pipeline.

**Three core use cases:**

1. **Sign Validation** — Verify that motion scripts in the database are physically plausible (joint limits, reachability, timing) before deploying to hardware.
2. **AI Model Evaluation** — Batch-test AI-generated motion scripts (from Professor Lin's model) against reference signs from the database, producing quantitative metrics for the paper (joint tracking error, execution success rates).
3. **Visual Demonstration** — Generate 3D animated visualizations of signs for presentations, the paper, and human evaluation.

---

### 12b. Module Structure

```
src/fk_tool/
├── __init__.py          # Package marker
├── __main__.py          # Entry point for python -m src.fk_tool
├── config.py            # Robot dimensions, joint calibration, evaluation thresholds, visualization defaults
├── models.py            # Dataclasses: ParsedSign, ParsedKeyframe, EvalIssue, SignEvaluation
├── fk_engine.py         # Numpy FK engine — 5-DOF kinematic chain (direct MATLAB port)
├── servo_mapper.py      # Bidirectional servo degrees ↔ joint radians conversion
├── sign_parser.py       # Schema validation, keyframe normalization, hold-forward resolution
├── loaders.py           # JSON file loader, MongoDB loader, AI output loader
├── evaluator.py         # 6 evaluation checks + sign comparison engine (AI vs reference)
├── visualizer.py        # Matplotlib 3D plotting: static poses, animated signs, comparison, batch thumbnails
├── report.py            # Console summary, CSV export, HTML report, comparison reporting
├── cli.py               # Argparse CLI with evaluate, visualize, compare subcommands
└── tests/
    ├── test_smoke.py        # FK engine, servo mapper, sign loading (9 tests)
    ├── test_evaluator.py    # Evaluation checks: valid, bad servo, bad timing, batch (6 tests)
    └── test_compare.py      # AI vs reference comparison logic (7 tests)
```

**Total: 22 unit and integration tests.**

---

### 12c. FK Kinematic Chain

The tool models a **5 degree-of-freedom (DOF) kinematic chain** per arm using homogeneous 4x4 transformation matrices chained together. This is a line-for-line port of the MATLAB `PlotRobLinks` function.

| Joint | Name                 | Motion                       | Transform Details                                    |
|-------|----------------------|------------------------------|------------------------------------------------------|
| q1    | Shoulder swing       | Flexion/extension            | Rotation about X axis, no translation                |
| q2    | Shoulder abduction   | Raise arm away from body     | Rotation about Y axis, translate X by 1.5 inches     |
| q3    | Elbow flexion        | Bicep curl motion            | Rotation about X axis, translate Z by -15 inches     |
| q4    | Wrist flexion        | Wrist bend (Italian chef)    | Rotation about X axis, translate Z by -10 inches     |
| q5    | Wrist pronation      | Wrist rotation (pour soup)   | Rotation about Z axis, translate Z by -1.5 inches    |

**Chain computation:** `T_world = T01 @ T12 @ T23 @ T34 @ T45`. Joint positions are extracted from column 3 (translation vector) of each cumulative transform.

**Servo group to joint mapping:**

| Servo Group | Joint         |
|-------------|---------------|
| LS[0] / RS[0] | q1 — shoulder swing |
| LS[1] / RS[1] | q2 — shoulder abduction |
| LE[0] / RE[0] | q3 — elbow flexion |
| LW[0] / RW[0] | q4 — wrist flexion |
| LW[1] / RW[1] | q5 — wrist pronation |
| L / R (5 each) | Fingers — not in FK model, stored as metadata |

**Link lengths (inches):** Shoulder offset = 1.5, Upper arm = 15.0, Forearm = 10.0, Wrist = 1.5. Shoulder X offset from body center = 7.0 per side.

---

### 12d. Servo-to-Radian Mapping

The default conversion formula is:

```
joint_rad = (servo_deg - neutral_deg) * scale * (pi / 180)
```

**Current default assumption:** `neutral_deg = 90`, `scale = 1.0` for all joints. This means servo 90° corresponds to 0 radians (arm hanging straight down), servo 0° = -π/2 rad, servo 180° = +π/2 rad.

This mapping is configurable per-joint in `config.py` via the `JOINT_CALIBRATION` dictionary, which stores `neutral_servo_deg`, `scale`, `min_rad`, and `max_rad` for each of the 5 joints.

> **ACTION ITEM — REQUIRES CONFIRMATION FROM PROFESSOR LAMACK / ENGINEERING TEAM:**
> The default 90° = 0 rad mapping is an assumption. The actual neutral positions, scale factors (some joints may be inverted), and mechanical limits need to be measured on the physical robot. Until confirmed, the tool produces correct *relative* motion but absolute joint positions may be offset. Changing the calibration requires editing only `config.py` — all other modules read from it.

---

### 12e. CLI Usage

Run with `python -m src.fk_tool <subcommand>`.

**Evaluate — Check signs for physical plausibility:**

```bash
# Evaluate all signs from a JSON file, generate HTML report
python -m src.fk_tool evaluate --input src/signs/signs_to_seed.json --report output.html

# Evaluate a single sign
python -m src.fk_tool evaluate --input src/signs/signs_to_seed.json --token HELLO

# Evaluate from MongoDB (all signs)
python -m src.fk_tool evaluate --source mongodb --report full_eval.html

# Evaluate specific tokens from MongoDB
python -m src.fk_tool evaluate --source mongodb --tokens HELLO THANKS PLEASE --report subset.csv
```

**Visualize — 3D stick-figure rendering:**

```bash
# Static first-keyframe plot
python -m src.fk_tool visualize --input src/signs/signs_to_seed.json --token HELLO --save hello.png

# Animated sign (saves as GIF)
python -m src.fk_tool visualize --input src/signs/signs_to_seed.json --token HELLO --animate --save hello.gif

# Visualize directly from MongoDB
python -m src.fk_tool visualize --source mongodb --token HELLO --animate --save hello.gif
```

**Compare — AI-generated vs reference signs:**

```bash
# Compare AI output against reference JSON file
python -m src.fk_tool compare --ai-input ai_signs.json --ref-input src/signs/signs_to_seed.json --report comparison.html

# Compare AI output against MongoDB reference
python -m src.fk_tool compare --ai-input ai_signs.json --ref-source mongodb --report comparison.csv
```

Report format is auto-detected: `.html` generates a self-contained sortable HTML report, `.csv` generates a spreadsheet-compatible CSV.

---

### 12f. Evaluation Metrics

The evaluator runs 6 checks on each sign. Each produces issues at FAIL level (sign is physically implausible) or WARN level (sign is suspicious but not broken).

| Check                     | Level | Description                                                       |
|---------------------------|-------|-------------------------------------------------------------------|
| Servo range               | FAIL  | Any servo value outside [0, 180] degrees                          |
| Joint limits              | FAIL  | Any joint angle outside calibrated min/max radians                |
| Timing                    | FAIL  | Non-monotonic keyframe times, first time ≠ 0.0, last ≠ duration  |
| Angular velocity          | WARN  | Any joint moves faster than 500 deg/s between keyframes           |
| Duration                  | WARN  | Sign duration outside [0.3s, 5.0s] range                         |
| Keyframe completeness     | WARN  | First keyframe has no servo group data at all                     |

A sign **passes** if it has zero FAIL-level issues. Summary metrics include: max angular velocity, number of keyframes, duration, and which arm(s) are used.

---

### 12g. AI Comparison Metrics

When comparing AI-generated signs against database reference signs (matched by token):

| Metric                 | Description                                                                  |
|------------------------|------------------------------------------------------------------------------|
| Joint angle MAE        | Mean absolute error in radians across all joints and keyframes (nearest-time matching). This is the "joint tracking error" metric for the paper. |
| Duration difference    | Absolute difference in sign duration (seconds)                               |
| Keyframe count diff    | Absolute difference in number of keyframes                                   |
| Arm agreement          | Whether both signs use the same arm(s) — boolean                             |
| Both passed            | Whether both AI and reference signs pass evaluation independently            |

The comparison report ranks signs by MAE to identify the worst-accuracy AI translations.

---

### 12h. Configuration

All physical parameters, calibration values, and evaluation thresholds are centralized in `src/fk_tool/config.py`. Key constants:

| Constant                          | Value    | Description                              |
|-----------------------------------|----------|------------------------------------------|
| `SHOULDER_OFFSET_LENGTH`          | 1.5 in   | T12 translation (shoulder joint spacing) |
| `UPPER_ARM_LENGTH`                | 15.0 in  | T23 translation (shoulder to elbow)      |
| `FOREARM_LENGTH`                  | 10.0 in  | T34 translation (elbow to wrist)         |
| `WRIST_LENGTH`                    | 1.5 in   | T45 translation (wrist to hand tip)      |
| `SHOULDER_X_OFFSET`               | 7.0 in   | Distance from body center to shoulder    |
| `SERVO_MIN_DEGREES`               | 0        | Minimum valid servo angle                |
| `SERVO_MAX_DEGREES`               | 180      | Maximum valid servo angle                |
| `MAX_ANGULAR_VELOCITY_DEG_PER_SEC`| 500      | Physical servo speed limit               |
| `MIN_SIGN_DURATION_SEC`           | 0.3 s    | Shortest reasonable sign                 |
| `MAX_SIGN_DURATION_SEC`           | 5.0 s    | Longest reasonable sign                  |

Joint calibration defaults: all joints use `neutral = 90°`, `scale = 1.0`. Elbow range is [0, 135°], wrist flexion is [±70°], all others are [±90°].

---

### 12i. Pending Calibration

The following items must be confirmed before the tool's absolute joint positions match the physical robot. **The tool works correctly for relative motion and all evaluation checks today** — only absolute positioning requires calibration.

1. **Servo neutral point per joint** — Is 90° truly the neutral (0 radian) position for every servo? Some servos may have different neutral positions.
2. **Scale factor and direction per joint** — Are any joints inverted (servo increase = joint angle decrease)? This would require `scale = -1.0` for that joint in `config.py`.
3. **Actual mechanical joint limits** — The servos support 0-180° but the physical arm may have tighter limits. Need measured values per joint.
4. **Right arm mirroring convention** — The tool currently negates q2 (shoulder abduction) for the right arm so that abduction goes outward on both sides. This needs visual confirmation with a known two-handed sign.

**Impact if uncalibrated:** Signs will look correct in relative motion (movements track properly) but may be offset or flipped in absolute position. **Fix is a one-file change** in `config.py` — no other module needs modification.

---