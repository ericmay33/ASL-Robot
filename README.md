# ASL Robot — "Fred"

> **Quinnipiac University · CSC 491 Senior Project · Spring 2026**

Fred is a real-time English-to-American-Sign-Language interpreter built around two custom-engineered humanoid robotic arms. The system listens through a microphone, transcribes speech, translates the English into ASL gloss tokens with a fine-tuned transformer, fetches the corresponding motion data from a MongoDB sign library, and streams that motion as keyframed JSON to a pair of ESP32 controllers — all while a sentiment-aware face display matches the speaker's emotion in real time.

The project's goal is to demonstrate that an end-to-end "speech in, signed motion out" pipeline can be built from off-the-shelf components and open ML models, and to produce a tangible communication aid that translates English-language audio into expressive ASL output.

## Demo at a glance

```
You say:    "Hey Fred, how are you doing today?"
                        │
                ┌───────▼────────┐
                │  Google STT    │  → "how are you doing today"
                └───────┬────────┘
                        │
            ┌───────────▼──────────┐
            │  T5 ASL-gloss model  │  → ["HOW", "YOU", "DO"]
            └───────────┬──────────┘
                        │
            ┌───────────▼──────────┐
            │  MongoDB sign lookup │  → motion JSON for HOW, YOU, DO
            └───────────┬──────────┘
                        │
        ┌───────────────▼───────────────┐
        │  motion_io → ESP32 (left+right) │
        └───────────────┬───────────────┘
                        │
                Robot signs the phrase,
                face shows "question" emotion
```

## System architecture

The pipeline runs as four daemon worker threads coordinated by a single `FileIOManager`. Tkinter's main loop owns the main thread for the emotion GUI; the workers communicate through queue / event pairs and shut down cooperatively on `Ctrl+C`.

```
                                ┌───────────────────────┐
                                │     FileIOManager     │
                                │  (queues + events)    │
                                └──────────┬────────────┘
                                           │
   ┌───────────────┐    ┌───────────────┐  │  ┌───────────────┐    ┌───────────────┐
   │   stt_io      │ ─► │    ai_io      │ ─┼─►│    db_io      │ ─► │   motion_io   │
   │ Google / Whi. │    │ T5 → tokens   │  │  │ Mongo lookup  │    │ Serial → ESP32│
   │               │    │ + emotion AI  │  │  │ + spelling    │    │ + emotion GUI │
   └───────────────┘    └───────────────┘  │  └───────────────┘    └───────────────┘
                                           │
                                           ▼
                              Tkinter face display (main thread)
```

Each producer pushes onto a `queue.Queue` and `set()`s a paired `threading.Event`; consumers `wait(timeout=0.5)` so they can periodically check `file_io.shutdown` and exit promptly. The motion thread is the one place the data fan-out splits — keyframes containing both `L*` and `R*` keys are sent to both ESP32s, single-arm signs go to one, and rest poses are auto-injected when the active arm changes.

### Why this shape?

A single-process synchronous pipeline would stall the microphone every time the T5 model ran inference, and the Tkinter GUI cannot be touched from a background thread. The four-stage queue setup decouples stages with vastly different latency profiles — STT streams continuously, AI translation is bursty (250–600 ms), DB lookups are sub-millisecond once warm, and motion execution is bounded by physical arm speed (≈2 s per sign). Buffering between them lets each stage run at its natural rate without blocking the others.

## What the robot does (today)

- **187 hand-authored signs** in the MongoDB library (`src/signs/signs_to_seed.json`), spanning common conversational vocabulary (greetings, family, food, time/date, common verbs, courtesy phrases, alphabet & digits).
- **Fingerspelling fallback** — any English word the gloss model emits that isn't in the sign DB is automatically signed letter-by-letter (case-insensitive lookup against the alphabet entries).
- **Bilateral & one-handed signs** — keyframes declare which hand they target via key prefixes (`L*` / `R*`); the motion router sends to one or both controllers as needed and rests the inactive arm.
- **Emotion-matched face** — every chunk of speech is independently classified into one of ten emotions (`anger`, `disgust`, `fear`, `joy`, `neutral`, `pain`, `question`, `sadness`, `surprise`, `teeth`-as-emphasis) and a portrait fades in synchronously with each token's motion.
- **Wake / sleep words** — the robot only acts on speech bracketed by `"fred"` / `"hey fred"` / `"frederick"` and stops on `"fred stop"` / `"thank you fred"`.

## Hardware

Each arm is independently controlled by an ESP32-DEVKIT board over USB serial (115 200 baud). Per arm:

| Joint group | Actuators | JSON key | Notes |
|---|---|---|---|
| Hand (fingers) | 5 servos | `L` / `R` | Thumb, index, middle, ring, pinky |
| Wrist | 2 servos | `LW` / `RW` | Rotation, flexion/extension |
| Elbow | 1 servo | `LE` / `RE` | Flexion |
| Shoulder | 2 NEMA-17 steppers (A4988 drivers) | `LS` / `RS` | Internal/external rotation (36:1 gearbox) + flexion/elevation (125:1 gearbox) |

**Total per arm:** 8 servos + 2 steppers. **Total robot:** 16 servos + 4 steppers.

The shoulder steppers use 8× microstepping plus heavy gearboxes to deliver enough torque to lift the rest of the arm; firmware constants `ROTATION_STEPS_PER_DEG = 320` and `ELEVATION_STEPS_PER_DEG = 222.22` (i.e. `3200 × 125 / 360`) convert the JSON's 0–180° "shoulder angles" into stepper steps. Servos run on `ESP32Servo` with a 2 ms inter-step delay, interpolating between keyframe angles 1° at a time. Steppers run on `AccelStepper` non-blocking with `setMaxSpeed(6000)` / `setAcceleration(5000)` and advance once per servo step iteration so the whole arm finishes a keyframe together.

**Power-on pose matters.** The current firmware does not home the steppers against limit switches — it tracks position from `0` on boot, so power Fred up with both arms in the neutral / rest pose (shoulders square, arms at sides). Restoring limit-switch homing is on the future-work list.

### Communication protocol

Python sends one-line JSON commands per sign, terminated with `\n`. The ESP32 firmware enqueues up to three commands at a time, executes them sequentially, and prints `ACK` after each motion completes. The Python motion thread blocks the next send on the previous `ACK` (8 s timeout fallback), so commands never overlap on a single arm.

## Setup

Requires Python 3.10+, [PlatformIO](https://platformio.org/) (for firmware), and a MongoDB instance (Atlas or local).

### 1. Python dependencies

```bash
pip install -r requirements.txt
```

Pulls `pymongo`, `python-dotenv`, `google-cloud-speech`, `google-auth`, `pyaudio`, `pyserial`, `sounddevice`, `torch`, `torchaudio`, `transformers`, `openai-whisper`, `numpy`, and `pillow`.

The HuggingFace models (~250 MB T5 gloss + ~330 MB DistilRoBERTa) download on first run. The emotion classifier loads with `local_files_only=True`, so the model must be cached before the live pipeline starts.

### 2. Environment variables

Create `.env` in the project root:

```ini
MONGODB_URI=mongodb+srv://<user>:<pass>@<cluster>.mongodb.net/
MONGODB_DB_NAME=ASLSignsDB
GOOGLE_APPLICATION_CREDENTIALS=stt_key_file.json
EVAN_HUGGING_FACE_LOGIN=hf_xxxxxxxxxxxxxxxxxxxxxxxxxx
GEMINI_API_KEY=unused
```

`GEMINI_API_KEY` is still validated by `settings.py` even though no code reads it — set it to any non-empty value. Optional overrides: `STT_ENGINE` (`cloud` / `local`), `LOCAL_STT_MODEL`, `LOCAL_STT_DEVICE`, `ASL_LEFT_PORT`, `ASL_RIGHT_PORT`.

Place your Google Cloud service account key in the project root as `stt_key_file.json`. Both `.env` and `stt_key_file.json` are gitignored.

### 3. Seed the sign database

```bash
python -m src.signs.seed_signs
```

This reads `src/signs/signs_to_seed.json` and writes every entry into the `signs` collection of the configured MongoDB database. To list what's in the DB:

```bash
python -m src.signs.listsigns
```

### 4. Flash ESP32 firmware

```bash
cd src/microcontrollers
pio run -e left_arm  -t upload
pio run -e right_arm -t upload
```

PlatformIO automatically installs `madhephaestus/ESP32Servo`, `bblanchon/ArduinoJson` (^7.4.2), and `waspinator/AccelStepper` (^1.64.0).

## Running

### Full system

```bash
python -B -m src.main
```

- Say a wake phrase (`"fred"`, `"hey fred"`, `"frederick"`) to activate.
- Speak your sentence — the robot translates and signs it; the face screen reflects sentiment.
- Say `"fred stop"` or `"thank you fred"` to deactivate.
- `Ctrl+C` shuts threads down cleanly and closes serial ports.

### Sign demo (no STT, no AI)

```bash
python -B -m src.testing.sign_demo
```

A modular CLI for hardware/calibration testing. Type whitespace-separated tokens at the `sign>` prompt — each is looked up in MongoDB (case-insensitive) or fingerspelled if unknown.

```text
sign> HELLO
sign> hello friend
sign> XYZ
sign> quit
```

Useful flags:

| Flag | Purpose |
|---|---|
| `--dry-run` | Print the resolved motion JSON to stdout; **do not** open serial. |
| `--left-port`, `--right-port` | Override the COM ports (defaults `COM8` and `COM4`; also `ASL_LEFT_PORT` / `ASL_RIGHT_PORT` env vars). |

This module sets `ASL_SIGN_DEMO=1` before importing settings, so only `MONGODB_URI` and `MONGODB_DB_NAME` are required — no Google STT or HuggingFace credentials needed.

## Forward-kinematics evaluation tool

The `src.fk_tool` module is a standalone offline utility that validates and visualizes signs *without* touching the robot. It implements a 5-DOF chain per arm: shoulder swing → shoulder abduction → elbow flexion → wrist flexion → wrist pronation, using 4×4 homogeneous transformation matrices.

### Subcommands

```bash
python -m src.fk_tool evaluate --input src/signs/signs_to_seed.json
python -m src.fk_tool evaluate --source mongodb --tokens HELLO THANK_YOU --report eval/report.html
python -m src.fk_tool visualize --input src/signs/signs_to_seed.json --token HELLO
python -m src.fk_tool visualize --input src/signs/signs_to_seed.json --token HELLO --animate --save eval/gifs/HELLO.gif
python -m src.fk_tool compare --ai-input ai_signs.json --ref-source mongodb --report eval/comparison.html
```

Subcommands: `evaluate` (validate a sign batch), `visualize` (3-D stick figure, optionally animated), and `compare` (AI-generated signs vs. reference library, MAE in radians).

### Evaluation checks (per sign)

| Check | Severity | What it catches |
|---|---|---|
| Servo range | FAIL | Any servo value outside [0°, 180°] |
| Joint limits | FAIL | Joint angles exceeding mechanical safe-zone calibration |
| Timing | FAIL | First frame ≠ 0.0, non-monotonic times, last frame > duration |
| Angular velocity | WARN | Any servo asked to move > 500 °/s between adjacent frames |
| Duration | WARN | Sign duration outside 0.3–5.0 s |
| Completeness | WARN | First keyframe declares no servo data |

Comparison mode also computes per-sign **joint-angle MAE** (radians, nearest-time keyframe matching), duration delta, keyframe-count delta, and arm-agreement.

Run the FK test suite with `pytest src/fk_tool/tests` (22 tests).

## Sign data schema

Every sign is one MongoDB document. The schema is intentionally simple — a list of timestamped keyframes, each declaring servo target angles per joint group. Omitted groups in a keyframe **hold** their previous position (firmware and `sign_parser.py` both implement this hold-forward semantics).

```json
{
  "token": "HELLO",
  "type": "DYNAMIC",
  "duration": 2.0,
  "keyframes": [
    {
      "time": 0.0,
      "L":  [180, 0, 0, 0, 0],
      "R":  [0, 0, 0, 0, 0],
      "LW": [90, 90],
      "RW": [90, 90],
      "LE": [90],
      "RE": [90],
      "LS": [90, 90],
      "RS": [90, 90]
    },
    { "time": 1.0, "LW": [120, 60], "RW": [60, 120] }
  ]
}
```

`type` is `STATIC` (single-pose) or `DYNAMIC` (animated). `L`/`R` are the 5 finger angles, `LW`/`RW` are wrist `[rotation, flexion]`, `LE`/`RE` are elbow flexion, `LS`/`RS` are shoulder `[rotation, elevation]`.

## Repository layout

```
ASL-Robot/
├── src/
│   ├── main.py
│   ├── config/
│   ├── database/
│   ├── speech_to_text/
│   ├── text_to_ASL/
│   ├── text_to_emotion/
│   ├── io/
│   ├── signs/
│   ├── cache/
│   ├── testing/
│   ├── microcontrollers/
│   └── fk_tool/
├── eval/
├── requirements.txt
└── README.md
```

## Project history & lessons learned

This was a year-long project; the stack changed materially as we learned more.

- **Original AI translator: Google Gemini.** We started with `google-genai` calls but moved to a fine-tuned T5 model (`AchrafAzzaouiRiceU/t5-english-to-asl-gloss`) once it became clear that gloss generation needed reproducibility, latency control, and offline capability. The post-processing layer (idiom phrase mapping, number/word substitution, WH-question reordering) was added incrementally as we discovered failure modes.
- **Original shoulder actuator: standard servos.** They couldn't lift the arm reliably under load, so we redesigned the shoulder around NEMA-17 steppers with two cascaded gearboxes per axis. The JSON schema kept the 0–180° "angle" convention and we just changed the conversion in firmware.
- **Original homing: limit-switch routine on every boot.** Caused regressions when arms were already in awkward poses; the team chose to revert to position-tracking-from-zero with a power-on neutral-pose convention. Limit-switch homing is on the future-work list.
- **Original GUI: a single emotion call per utterance.** Long sentences felt monotone, so we sliced them into 10-word windows, classified each, and aligned chunk emotions to gloss tokens proportionally — the face now reacts mid-sentence.
- **Threading model.** A naïve single-thread pipeline blocked the microphone whenever T5 inference ran; the queue/event-driven worker model dropped end-to-end latency from ~3 s to ~700 ms per sign in the best case.

## Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| `[MOTION_IO] ⚠ ... connection failed` | Wrong COM port. Check Device Manager / `/dev/tty*`; defaults are `COM8` (left) and `COM4` (right). Override with `ASL_LEFT_PORT` / `ASL_RIGHT_PORT` env vars. |
| Shoulders are off-position from the start | The arms weren't in the neutral pose at boot. Power-cycle both ESP32s with the arms hanging straight at the sides. |
| `Missing environment variables` on startup | `settings.py` validates eagerly. Check `.env` includes `MONGODB_URI`, `MONGODB_DB_NAME`, `GOOGLE_APPLICATION_CREDENTIALS`, `GEMINI_API_KEY` (any non-empty), and `EVAN_HUGGING_FACE_LOGIN`. |
| Emotion classifier fails on first run | The pipeline loads the HuggingFace model with `local_files_only=True`. Run with internet access once to populate the cache, or change that flag locally during initial setup. |
| `ACK timeout from LEFT/RIGHT controller` | The firmware took longer than 8 s to finish a motion (long duration sign, or a stepper jam). The Python side continues anyway; check for mechanical binding. |
| Speech recognition silent / no transcripts | Mic permissions, wrong default audio device, or `stt_key_file.json` invalid. `STT_ENGINE=local` switches to Whisper as a sanity test. |

## Future work

- Re-introduce limit-switch homing for the shoulder steppers.
- Expand the sign library beyond 187 entries; collect and approve user-contributed signs.
- Replace the 8 s ACK timeout fallback with adaptive per-sign budgets derived from `duration` × safety factor.
- Stream tokens progressively from STT instead of waiting for sentence boundaries (would cut perceived latency further).
- Re-evaluate and re-tune signs against the FK tool's joint-limit checks; some early signs were authored before the evaluator existed.

