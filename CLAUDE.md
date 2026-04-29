# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

ASL Robot: a real-time English-to-ASL translation pipeline that drives two ESP32-controlled robotic arms. Speech is transcribed, translated to ASL gloss tokens, looked up in MongoDB, then streamed as keyframe motion scripts over serial. Sentiment is classified in parallel and shown on a Tkinter face display.

**AI models in use today** (the older Gemini-based design is gone — `GEMINI_API_KEY` is still validated in `settings.py` but nothing reads it):
- English → ASL gloss: HuggingFace T5 model `AchrafAzzaouiRiceU/t5-english-to-asl-gloss` (`src/text_to_ASL/translate_AI.py`).
- Text → emotion: HuggingFace `j-hartmann/emotion-english-distilroberta-base` plus keyword overrides for question/pain/teeth (`src/text_to_emotion/emotion_AI.py`). This module calls `huggingface_hub.login(EVAN_HUGGING_FACE_LOGIN)` at import time, so that env var must be set in `.env` for the full pipeline to start.

## Commands

Run from the repo root. Always use `python -B -m <module>` (the codebase relies on `src.` package imports — never run scripts by path).

| Task | Command |
|------|---------|
| Run full system | `python -B -m src.main` |
| Modular sign-by-sign CLI (no STT/AI) | `python -B -m src.testing.sign_demo` |
| Sign demo, dry run (no serial) | `python -B -m src.testing.sign_demo --dry-run` |
| Seed MongoDB from `signs_to_seed.json` | `python -m src.signs.seed_signs` |
| List signs in DB | `python -m src.signs.listsigns` |
| FK tool (evaluate / visualize / compare) | `python -m src.fk_tool <subcommand>` |
| Run FK tool tests | `pytest src/fk_tool/tests` (or a single file: `pytest src/fk_tool/tests/test_evaluator.py`) |
| Flash left-arm firmware | `cd src/microcontrollers && pio run -e left_arm -t upload` |
| Flash right-arm firmware | `cd src/microcontrollers && pio run -e right_arm -t upload` |

`src.testing.sign_demo` sets `ASL_SIGN_DEMO=1` before importing settings; in that mode only `MONGODB_URI` and `MONGODB_DB_NAME` are required (Google STT and Gemini keys are not validated). Each input line is split on whitespace and every token is queued (case-insensitive — `hello` and `HELLO` both match the same DB document). Unknown tokens fall back to fingerspelling. Bilateral signs route to both ESP32s automatically via `motion_io.get_arms_for_script`. Use this for hardware/pipeline testing without loading any AI models or running STT.

## Architecture

### Worker-thread pipeline

`src/main.py` spins up four daemon threads coordinated by a single `FileIOManager` (`src/io/fileIO.py`). Tkinter's `mainloop` runs on the main thread for the emotion GUI. Data flows one direction:

```
stt_io → ai_io → db_io → motion_io
   ↓        ↓       ↓         ↓
 stt_line  asl_token  motion   serial → ESP32s
 _queue    _queue    _queue
```

Each stage waits on a `threading.Event` paired with its input queue (`stt_new_signal`, `asl_new_signal`, `motion_new_signal`). Producers `push_*` (which `set()` the event); consumers `pop_*` (which `clear()` the event when the queue drains). Shutdown is cooperative via `file_io.shutdown` — every loop checks `shutdown.is_set()` between work items, with `wait(timeout=0.5)` so threads exit promptly on Ctrl+C.

When adding a new pipeline stage or queue, follow the existing `push_X` / `pop_X` + paired `Event` pattern in `FileIOManager` rather than introducing a new synchronization primitive.

**Emotion GUI is the one exception.** `main.py` constructs a plain `queue.Queue` and passes it as the second positional arg to `run_motion(file_io, emotion_gui_queue)`. Inside `motion_io`, emotion strings are drained from `file_io.motion_emotion_queue` and forwarded into the GUI queue, which Tkinter polls via `root.after(50, poll_emotion_queue)`. Tkinter is not thread-safe — never call `show_emotion` from a worker thread; always go through this queue.

### Token resolution

`src/io/sign_resolution.py` is the single source of truth for "ASL token → motion script(s)":
1. Look up `token` in MongoDB via `get_sign_by_token` — if found, queue that one document.
2. Otherwise, fingerspell each character through `src/cache/fingerspelling_cache.py`.

Both `db_io` (the live thread) and `sign_demo` (the manual CLI) call into this module. Don't duplicate the lookup-then-fingerspell logic elsewhere.

### Motion routing to two controllers

`motion_io.py` opens two serial connections. The actual code defaults are **`COM8` for left and `COM4` for right** (`run_motion(... left_port="COM8", right_port="COM4")`); `sign_demo.py` uses the same defaults. Override via `--left-port`/`--right-port` flags or `ASL_LEFT_PORT`/`ASL_RIGHT_PORT` env vars. Note: the `sign_demo.py` `--help` strings still say "default: ASL_LEFT_PORT or COM3" — that text is stale; trust the code defaults (`COM8` / `COM4`).

`get_arms_for_script` inspects the keyframe servo-group keys and decides which controller(s) to send to — left keys are `{L, LW, LE, LS}`, right keys are `{R, RW, RE, RS}`. A single-arm sign is sent to only one controller; symmetric signs go to both. Rest poses (`REST_LEFT`/`REST_RIGHT` from `src/cache/rest_cache.py`) are auto-injected when motion switches from a two-arm or opposite-side context to a single-arm sign.

Both controllers ACK each command (`Serial.println("ACK")` in firmware after the keyframe loop completes); `wait_ack_then_send` blocks the next send on the previous ACK with an 8-second `ACK_TIMEOUT` fallback. Inter-motion delay is `FINGERSPELL_POST_DELAY=30 ms` for single-character tokens and `SIGN_POST_DELAY=150 ms` otherwise.

### Sign data schema

`src/signs/signs_to_seed.json` is the canonical sign source; `seed_signs.py` writes it to the `signs` MongoDB collection. Schema:

```json
{
  "token": "HELLO",
  "type": "STATIC" | "DYNAMIC",
  "duration": 2.0,
  "keyframes": [
    {"time": 0.0, "L": [...5], "R": [...5], "LW": [...2], "RW": [...2], "LE": [...1], "RE": [...1], "LS": [...2], "RS": [...2]}
  ]
}
```

All servo groups are **optional per keyframe**: omitted groups hold their previous position (the firmware and `sign_parser.py` both implement hold-forward semantics — match that contract when generating or editing sign data).

### Hardware

**16 servos + 4 steppers** total. Per arm: 5 hand + 2 wrist + 1 elbow = **8 servos**, plus 2 shoulder **steppers** (A4988 drivers, NEMA-17-class) for rotation and flexion/elevation. The JSON schema still represents shoulders as `LS`/`RS` arrays of "servo angles" (0–180°); the firmware converts those to stepper steps via `ROTATION_STEPS_PER_DEG=320` and `ELEVATION_STEPS_PER_DEG=222.22` (3200 × 125 / 360, reflecting the 125:1 elevation gearbox).

**Steppers do NOT home against limit switches at boot.** The current firmware (post-revert at commit `5de3d71`) has no `homeAxis()` routine; it tracks position via `static long prevRotationSteps`/`prevElevationSteps` initialized to `0`, so **the arms must already be in the neutral pose at power-on** for stepper coordinates to be accurate. (Earlier commits had homing logic — it was reverted to recover working behavior; if you re-add homing, restore the limit-switch wiring and a `homeAxis` call in `setup()`.)

Both `left_arm.cpp` and `right_arm.cpp` are essentially mirrored — same 325-line skeleton, only the keyframe key prefixes (`L*` vs `R*`) and pin assignments differ. ESP32 firmware uses `ESP32Servo`, `ArduinoJson` (^7.4.2), and `AccelStepper` (^1.64.0), declared in `platformio.ini`.

### STT engine selection

`src/speech_to_text/stt_factory.py` picks the engine from `STT_ENGINE` env var: `cloud` (Google Cloud Speech, default) or `local` (Whisper via `LOCAL_STT_MODEL` and `LOCAL_STT_DEVICE`). Wake words are `"fred"`, `"hey fred"`, `"frederick"`; sleep words are `"fred stop"`, `"thank you fred"`.

### Emotion display

The Tkinter GUI shows one of ten static face PNGs from `src/cache/emotions/` (`anger`, `disgust`, `fear`, `joy`, `neutral`, `pain`, `question`, `sadness`, `surprise`, `teeth`). `ai_io` aligns each emitted token with a chunk-level emotion derived from the originating sentence and pushes both onto the queue together; `motion_io` forwards the emotion into `emotion_gui_queue` *as it sends the matching motion* so face and arms stay in sync. The GUI does a 200 ms crossfade between faces and idles back to `neutral` after 3 s.

### Forward kinematics tool (`src/fk_tool`)

Standalone evaluator/visualizer that does **not** run as part of the live pipeline. 5-DOF chain per arm (q1 shoulder swing → q2 shoulder abduction → q3 elbow → q4 wrist flexion → q5 wrist pronation). `evaluator.py` enforces 6 checks: servo range 0–180°, joint limits, monotonic keyframe times, ≤500°/s angular velocity, duration 0.3–5.0 s, all required servo groups present. `loaders.py` can pull signs from JSON, MongoDB, or AI output — keep it as the single ingestion point.

## Conventions

- **Module entry only.** Run scripts via `python -m src.<package>.<module>`, never `python src/foo/bar.py`. Imports throughout the tree are absolute (`from src.io.fileIO import ...`) and break under direct path execution.
- **Settings load on import.** `src/config/settings.py` calls `SETTINGS.validate()` at module load. If you import `src.config.settings` from a tool that doesn't need all credentials, set `ASL_SIGN_DEMO=1` *before* the import (see `src/testing/sign_demo.py:32`).
- **`stt_key_file.json` and `.env`** are gitignored — never commit them.
- **MongoDB ObjectIds** appear in motion documents; when serializing for `--dry-run` output, use the `_json_default` helper in `sign_demo.py` (it `str()`s ObjectIds).
- **Required `.env` keys for `src.main`:** `MONGODB_URI`, `MONGODB_DB_NAME`, `GOOGLE_APPLICATION_CREDENTIALS` (path to `stt_key_file.json`), `GEMINI_API_KEY` (still validated even though unused — set it to any non-empty string), and `EVAN_HUGGING_FACE_LOGIN` (HuggingFace token for the emotion model; not validated by `settings.py` but `emotion_AI.py` calls `huggingface_hub.login` at import time).
