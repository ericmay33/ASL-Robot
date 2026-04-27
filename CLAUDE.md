# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

ASL Robot: a real-time English-to-ASL translation pipeline that drives two ESP32-controlled robotic arms (10 servos + steppers each). Speech is transcribed, translated to ASL gloss tokens via Gemini, looked up in MongoDB, then streamed as keyframe motion scripts over serial.

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

`motion_io.py` opens two serial connections. The actual code defaults are **`COM3` for left and `COM4` for right** (`run_motion(... left_port="COM3", right_port="COM4")`); override via `--left-port`/`--right-port` or `ASL_LEFT_PORT`/`ASL_RIGHT_PORT` env vars. Note: `src/testing/sign_demo.py`'s `--help` text claims `COM6` for the right port, but its actual `default=os.getenv("ASL_RIGHT_PORT", "COM4")` matches `motion_io` — treat `COM4` as the source of truth. `get_arms_for_script` inspects the keyframe servo-group keys and decides which controller(s) to send to — left keys are `{L, LW, LE, LS}`, right keys are `{R, RW, RE, RS}`. A single-arm sign is sent to only one controller; symmetric signs go to both. Rest poses (`REST_LEFT`/`REST_RIGHT` from `src/cache/rest_cache.py`) are loaded at startup.

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

**16 servos + 4 steppers**, not 20 servos (the README's "20 servos" claim is wrong). Per arm: 5 hand + 2 wrist + 1 elbow = **8 servos**, plus 2 shoulder **steppers** (A4988 drivers, NEMA-17-class). Both arms use steppers for shoulders — see `AccelStepper shoulderRotation` / `shoulderFlexion` in both `left_arm.cpp` and `right_arm.cpp`. The JSON schema still represents shoulders as `LS`/`RS` arrays of "servo angles" (0–180°); the firmware converts those to stepper steps via `ROTATION_STEPS_PER_DEG` / `ELEVATION_STEPS_PER_DEG`. Steppers home against limit switches at boot (`homeAxis`) — power-on must be in a homing-safe pose. ESP32 firmware uses `ESP32Servo`, `ArduinoJson`, and `AccelStepper` (declared in `platformio.ini`).

### STT engine selection

`src/speech_to_text/stt_factory.py` picks the engine from `STT_ENGINE` env var: `cloud` (Google Cloud Speech, default) or `local` (Whisper via `LOCAL_STT_MODEL` and `LOCAL_STT_DEVICE`). Wake words are `"fred"`, `"hey fred"`, `"frederick"`; sleep words are `"fred stop"`, `"thank you fred"`.

### Forward kinematics tool (`src/fk_tool`)

Standalone evaluator/visualizer that does **not** run as part of the live pipeline. 5-DOF chain per arm (q1 shoulder swing → q2 shoulder abduction → q3 elbow → q4 wrist flexion → q5 wrist pronation). `evaluator.py` enforces 6 checks: servo range 0–180°, joint limits, monotonic keyframe times, ≤500°/s angular velocity, duration 0.3–5.0 s, all required servo groups present. `loaders.py` can pull signs from JSON, MongoDB, or AI output — keep it as the single ingestion point.

## Conventions

- **Module entry only.** Run scripts via `python -m src.<package>.<module>`, never `python src/foo/bar.py`. Imports throughout the tree are absolute (`from src.io.fileIO import ...`) and break under direct path execution.
- **Settings load on import.** `src/config/settings.py` calls `SETTINGS.validate()` at module load. If you import `src.config.settings` from a tool that doesn't need all credentials, set `ASL_SIGN_DEMO=1` *before* the import (see `src/testing/sign_demo.py:32`).
- **`stt_key_file.json` and `.env`** are gitignored — never commit them.
- **MongoDB ObjectIds** appear in motion documents; when serializing for `--dry-run` output, use the `_json_default` helper in `sign_demo.py` (it `str()`s ObjectIds).
