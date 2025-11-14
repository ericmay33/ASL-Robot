# SeniorProjectASLRobot

An ASL (American Sign Language) Robot that converts spoken English into ASL signs using real-time speech recognition, AI translation, and robotic motion execution.

## 📁 Project Structure

```
ASL-Robot/
│
├── src/
│   ├── main.py                         # System Entry point
│   ├── Arduino.cpp                     # Arduino/ESP32 sketch for servo control
│   ├── config/
│   │   └── settings.py                 # Environment variable loading and validation
│   ├── database/
│   │   ├── db_connection.py            # MongoDB connection initlization
│   │   └── db_functions.py             # MongoDB database function/interaction
│   └── speech_to_text/
│       └── stt.py                      # Speech to text
│   └── text_to_ASL/
│       └── translate_AI.py             # AI text to ASL
│   └── io/
│       ├── ai_io.py                    # Thread translating lines to tokens
│       ├── db_io.py                    # Thread retreiving motions from database with tokens
│       ├── fileIO.py                   # File IO Manager
│       ├── motion_io.py                # Thread handling sending motion signs
│       └── stt_io.py                   # Thread handling STT 
│   └── signs/
│       ├── signs_to_seed.json          # All sign data json
│       └── seed_signs.py               # MongoDB Seeder Script
│  
├── README.md                           # Project overview and setup instructions
├── stt_key_file.json                   # Google Cloud credentials (not tracked in Git)
├── .env                                # Environment variables (not tracked in Git)
├── requirements.txt                    # Python dependencies
├── platformio.ini                      # PlatformIO configuration for Arduino/ESP32
└── translator.ipynb                    # Jupyter notebook for testing/development
```

## 🏗️ System Architecture

The system uses a **multi-threaded architecture** with four worker threads that communicate through a centralized `FileIOManager`:

1. **STT Thread** (`stt_io.py`): Listens for speech, detects wake words ("fred", "frederick", etc.), and streams transcribed text
2. **AI Thread** (`ai_io.py`): Translates English text to ASL gloss tokens using Gemini AI
3. **DB Thread** (`db_io.py`): Looks up sign motion data from MongoDB for each ASL token
4. **Motion Thread** (`motion_io.py`): Sends motion scripts to Arduino via serial communication

**Data Flow:**
```
Microphone → STT → English Text → AI Translation → ASL Tokens → Database Lookup → Motion Scripts → Arduino → Servo Motors
```

**Servo System:**
- **Current**: 5 servos for left hand (L) - finger and hand articulation
- **Future**: Full bilateral arm system with 20 servos total:
  - Hands (L, R): 10 servos (5 per hand)
  - Wrists (LW, RW): 4 servos (2 per wrist)
  - Elbows (LE, RE): 2 servos (1 per elbow)
  - Shoulders (LS, RS): 4 servos (2 per shoulder)

**Wake Word Activation:**
- Activate: Say "fred", "frederick", "freddy", "hey fred", or "fred please translate"
- Deactivate: Say "stop moving", "fred stop", or "thank you fred"

---

## ⚙️ 1. Installing Dependencies

Ensure Python 3.10+ is installed. Then, from the project root directory:

```bash
pip install -r requirements.txt
```

This will install:

* `pymongo` - MongoDB client for database operations
* `python-dotenv` - Environment variable loader
* `google-cloud-speech` - Google Cloud Speech-to-Text API client
* `google-auth` - Google authentication library
* `pyaudio` - Audio input/output for microphone access
* `google-genai` - Gemini AI API client for text translation
* `pyserial` - Serial communication with Arduino/ESP32


---

## 🔐 2. .env File Setup

Create a `.env` file in the project root directory with the following:

```
MONGODB_URI=mongodb+srv://<USERNAME>:<PASSWORD>@<YOUR_CLUSTER>.mongodb.net/
MONGODB_DB_NAME=ASLSignsDB

GOOGLE_APPLICATION_CREDENTIALS="stt_key_file.json"

GEMINI_API_KEY="your-gemini-api-key-here"
```

> **Note:** 
> - Replace `<USERNAME>` and `<PASSWORD>` with your MongoDB credentials
> - Replace `your-gemini-api-key-here` with your actual Gemini API key
> - The `.env` file should remain private and not tracked by Git
> - Credentials can be found in shared OneDrive folder

---

## 🔑 3. Speech-to-Text (STT) Credentials Setup

The Speech-to-Text module uses a **JSON key file** for secure authentication with the Google Cloud Speech-to-Text API. This file contains sensitive service account credentials and must be set up correctly.

### A. Obtain and Name the Key File

1. Locate the necessary Google Cloud Service Account JSON file (which contains the required credentials).
2. **Save this file** in the **root** of your project directory.
3. You **must** rename the file exactly as referenced in your `.env` file: `stt_key_file.json`.

### B. Authentication Process

* The environment variable **`GOOGLE_APPLICATION_CREDENTIALS`** tells the `google-auth` library where to find the key file.
* The `stt.py` module uses this path to securely authenticate to the Google API, ensuring credentials are not **hardcoded** into the application.

### C. Security Best Practice

* Verify that both **`stt_key_file.json`** and **`.env`** are explicitly listed in your `.gitignore` file to prevent sharing.

---

## 🏃 4. Database Seeding

Before running the system, you need to seed the database with ASL sign definitions:

```bash
python -m src.signs.seed_signs
```

This will:
- Load signs from `src/signs/signs_to_seed.json`
- Insert new signs into MongoDB
- Update existing signs if they've changed
- Remove signs from the database that are no longer in the JSON file

To reset the database and start fresh:
```bash
python -c "from src.signs.seed_signs import seed_signs; seed_signs(reset=True)"
```

## 🔌 5. Arduino/ESP32 Setup

### Hardware Requirements
- Arduino Mega 2560 (or compatible board)
- Servos for ASL robot articulation:
  - **Current Implementation**: 5 servos for left hand (L) connected to pins 2, 3, 4, 5, 6
  - **Full System Design**: 
    - **L** (Left Hand): 5 servos - finger and hand articulation
    - **R** (Right Hand): 5 servos - finger and hand articulation
    - **LW** (Left Wrist): 2 servos - wrist rotation and flexion
    - **RW** (Right Wrist): 2 servos - wrist rotation and flexion
    - **LE** (Left Elbow): 1 servo - elbow flexion/extension
    - **RE** (Right Elbow): 1 servo - elbow flexion/extension
    - **LS** (Left Shoulder): 2 servos - shoulder rotation and elevation
    - **RS** (Right Shoulder): 2 servos - shoulder rotation and elevation
- USB serial connection to computer

### Firmware Installation

1. Install PlatformIO (if not already installed):
   ```bash
   pip install platformio
   ```

2. Upload the firmware to your Arduino:
   ```bash
   pio run -t upload
   ```

3. The firmware uses:
   - **VarSpeedServo** library for smooth servo movement
   - **ArduinoJson** library for parsing JSON commands
   - Command queue system (buffers up to 3 signs)
   - Serial communication at 115200 baud
   - **Current Implementation**: Supports 5 servos for left hand (L) only
   - **Future**: Will support full bilateral arm system (L, R, LW, RW, LE, RE, LS, RS)

### Serial Port Configuration

The motion I/O handler connects to the Arduino via serial. By default, it uses `/dev/cu.usbmodem1201` on macOS. To change the port, modify the `port` parameter in `src/io/motion_io.py`:

```python
def run_motion(file_io, port="/dev/cu.usbmodem1201", baud=115200):
```

**Finding your serial port:**
- **macOS/Linux**: `ls /dev/cu.*` or `ls /dev/tty.*`
- **Windows**: Check Device Manager for COM ports

## 🏃 6. Running the Project

Once setup is complete, you can run the project with the following command:

```bash
python -B -m src.main
```

The system will:
1. Initialize all threads (STT, AI, DB, Motion)
2. Start listening for wake words
3. Process speech when activated
4. Execute ASL signs on the robot

**Usage:**
- Say a wake phrase (e.g., "fred", "hey fred") to activate
- Speak your sentence
- The robot will translate and sign your words
- Say "stop moving" or "fred stop" to deactivate

## 📊 Sign Data Schema

Each sign in the database follows this schema. Currently, the system implements **L** (Left Hand) only, but the schema is designed to support full bilateral arm articulation.

### Current Implementation (Left Hand Only)

```json
{
  "token": "HELLO",
  "type": "DYNAMIC",
  "duration": 2.0,
  "keyframes": [
    { "time": 0.0, "L": [180, 0, 0, 0, 0] },
    { "time": 1.0, "L": [180, 20, 20, 20, 20] },
    { "time": 2.0, "L": [180, 0, 0, 0, 0] }
  ]
}
```

### Complete Schema (Full System Design)

```json
{
  "token": "HELLO",
  "type": "DYNAMIC",
  "duration": 2.0,
  "keyframes": [
    {
      "time": 0.0,
      "L": [180, 0, 0, 0, 0],           // Left Hand: 5 servos (finger/hand articulation)
      "R": [0, 0, 0, 0, 0],             // Right Hand: 5 servos (finger/hand articulation)
      "LW": [90, 90],                   // Left Wrist: 2 servos (rotation, flexion)
      "RW": [90, 90],                   // Right Wrist: 2 servos (rotation, flexion)
      "LE": [90],                       // Left Elbow: 1 servo (flexion/extension)
      "RE": [90],                       // Right Elbow: 1 servo (flexion/extension)
      "LS": [90, 90],                   // Left Shoulder: 2 servos (rotation, elevation)
      "RS": [90, 90]                    // Right Shoulder: 2 servos (rotation, elevation)
    }
  ]
}
```

### Field Descriptions

- **token**: ASL gloss token (uppercase)
- **type**: "STATIC" or "DYNAMIC"
  - **STATIC**: Single keyframe, held for the duration
  - **DYNAMIC**: Multiple keyframes, animated over the duration
- **duration**: Total sign duration in seconds
- **keyframes**: Array of servo positions over time
  - **time**: Timestamp in seconds (relative to sign start)
  - **L**: Array of 5 servo angles (0-180°) for left hand finger/hand articulation
  - **R**: Array of 5 servo angles (0-180°) for right hand finger/hand articulation
  - **LW**: Array of 2 servo angles (0-180°) for left wrist (rotation, flexion)
  - **RW**: Array of 2 servo angles (0-180°) for right wrist (rotation, flexion)
  - **LE**: Array of 1 servo angle (0-180°) for left elbow (flexion/extension)
  - **RE**: Array of 1 servo angle (0-180°) for right elbow (flexion/extension)
  - **LS**: Array of 2 servo angles (0-180°) for left shoulder (rotation, elevation)
  - **RS**: Array of 2 servo angles (0-180°) for right shoulder (rotation, elevation)

**Note**: All servo groups are optional in keyframes. Only include the servo groups that need to change for a given sign. Servo groups not specified in a keyframe will maintain their previous position.

## 🔧 Troubleshooting

### Serial Connection Issues
- Verify the correct serial port in `motion_io.py`
- Check that the Arduino is connected and powered
- Ensure the baud rate matches (115200)
- Verify the firmware is uploaded correctly

### Database Connection Issues
- Check that `MONGODB_URI` and `MONGODB_DB_NAME` are set correctly in `.env`
- Verify MongoDB network access and credentials
- Ensure the database has been seeded with signs

### Speech Recognition Issues
- Verify `GOOGLE_APPLICATION_CREDENTIALS` points to a valid JSON key file
- Check microphone permissions
- Ensure Google Cloud Speech-to-Text API is enabled

### AI Translation Issues
- Verify `GEMINI_API_KEY` is set correctly in `.env`
- Check that the Gemini API is enabled and has quota available

---
