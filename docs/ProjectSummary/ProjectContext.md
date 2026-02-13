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

**Recent Improvements (Sprint 5)**:

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

## 9. Recent Improvements (Sprint 5)

### Motion Pipeline Enhancements

1. **ACK-Based Synchronization** - Eliminated fixed delays, prevents queue overflow
2. **Smart Fingerspelling Delays** - 30ms between letters, 150ms between signs
3. **Intelligent Command Routing** - Only sends commands to necessary arm(s)
4. **Generalized Fingerspelling Fallback** - Any unknown word automatically fingerspelled
5. **Dual-Mode STT** - Choice between cloud (Google) or local (Whisper) speech recognition

### Performance Improvements

- **25% faster** overall execution
- **43% faster** fingerspelling (smooth letter flow)
- **50% reduction** in serial traffic for single-arm motions
- **100% elimination** of buffer overflow issues
- **Lower latency** with local STT (no network delay)

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