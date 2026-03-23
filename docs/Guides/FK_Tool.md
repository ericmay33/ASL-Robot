# FK Tool — Forward Kinematics Simulation & Evaluation

A Python tool for simulating, visualizing, and batch-evaluating ASL sign motion scripts for the ASL Robot project. Built as a direct port of Professor LaMack's MATLAB `PlotRobLinks` forward kinematics script.

---

## What This Tool Does

The ASL Robot performs sign language using servo-driven arms. Each sign is a JSON motion script containing keyframes of servo angles. This tool takes those motion scripts and:

1. **Simulates** the arm positions in 3D using forward kinematics (math that converts joint angles into physical positions)
2. **Evaluates** whether the motion is physically possible (servos in range, joints within limits, timing is valid, speed is realistic)
3. **Visualizes** the arm as an animated 3D stick figure
4. **Compares** AI-generated signs against reference signs from the database, producing accuracy metrics

You do **not** need the physical robot or Arduino hardware to use this tool. Everything runs in software.

---

## Quick Start

### Prerequisites

You need Python 3.10+ and these packages (already in the project's `requirements.txt`):

```
numpy
matplotlib
pymongo        # only needed for --source mongodb
python-dotenv  # only needed for --source mongodb
```

### Run Your First Evaluation

```bash
# From the ASL-Robot project root:

# Evaluate all 187 signs in the example seed file
python -m src.fk_tool evaluate --input src/signs/signs_to_seed.json

# Evaluate one specific sign
python -m src.fk_tool evaluate --input src/signs/signs_to_seed.json --token HELLO

# Generate a full HTML report (open in any browser)
python -m src.fk_tool evaluate --input src/signs/signs_to_seed.json --report eval_report.html
```

### Visualize a Sign

```bash
# Save a static image of the first keyframe
python -m src.fk_tool visualize --input src/signs/signs_to_seed.json --token HELLO --save hello.png

# Save an animated GIF of the full sign
python -m src.fk_tool visualize --input src/signs/signs_to_seed.json --token HELLO --animate --save hello.gif

# Open an interactive 3D matplotlib window (no --save)
python -m src.fk_tool visualize --input src/signs/signs_to_seed.json --token HELLO --animate
```

### Compare AI Signs Against Reference

```bash
# Compare AI output file against seed file
python -m src.fk_tool compare --ai-input ai_generated_signs.json --ref-input src/signs/signs_to_seed.json --report comparison.html

# Compare AI output against MongoDB database
python -m src.fk_tool compare --ai-input ai_generated_signs.json --ref-source mongodb --report comparison.csv
```

---

## Commands Reference

### `evaluate` — Check physical plausibility


| Flag                | Required     | Description                                      |
| ------------------- | ------------ | ------------------------------------------------ |
| `--input FILE`      | One of these | Path to a signs JSON file                        |
| `--source mongodb`  | is required  | Load signs from MongoDB instead                  |
| `--token TOKEN`     | No           | Evaluate only this one sign                      |
| `--tokens T1 T2 T3` | No           | Evaluate only these signs (MongoDB mode)         |
| `--report FILE`     | No           | Save report as `.csv` or `.html` (auto-detected) |


**Examples:**

```bash
python -m src.fk_tool evaluate --input signs.json
python -m src.fk_tool evaluate --input signs.json --token HELLO --report hello.csv
python -m src.fk_tool evaluate --source mongodb --report full_report.html
python -m src.fk_tool evaluate --source mongodb --tokens HELLO THANK-YOU PLEASE
```

### `visualize` — 3D arm rendering


| Flag               | Required     | Description                                                     |
| ------------------ | ------------ | --------------------------------------------------------------- |
| `--input FILE`     | One of these | Path to a signs JSON file                                       |
| `--source mongodb` | is required  | Load from MongoDB                                               |
| `--token TOKEN`    | Yes          | Which sign to visualize                                         |
| `--animate`        | No           | Animate through all keyframes (default: static first frame)     |
| `--save FILE`      | No           | Save to `.png`, `.gif`, or `.mp4` (default: interactive window) |


**Examples:**

```bash
python -m src.fk_tool visualize --input signs.json --token HELLO --save hello.png
python -m src.fk_tool visualize --input signs.json --token HELLO --animate --save hello.gif
python -m src.fk_tool visualize --source mongodb --token HELLO --animate
```

### `compare` — AI vs reference accuracy


| Flag                   | Required     | Description                          |
| ---------------------- | ------------ | ------------------------------------ |
| `--ai-input FILE`      | Yes          | Path to AI-generated signs JSON      |
| `--ref-input FILE`     | One of these | Path to reference signs JSON         |
| `--ref-source mongodb` | is required  | Load reference from MongoDB          |
| `--report FILE`        | No           | Save comparison as `.csv` or `.html` |


**Examples:**

```bash
python -m src.fk_tool compare --ai-input ai_out.json --ref-input seeds.json --report comp.html
python -m src.fk_tool compare --ai-input ai_out.json --ref-source mongodb --report comp.csv
```

---

## How It Works

### The Kinematic Chain

The tool models each arm as a 5-joint chain. Given servo angles from a motion script, it computes where each joint (shoulder, elbow, wrist, hand) sits in 3D space.

```
Shoulder Base → Shoulder Swing (q1) → Shoulder Abduction (q2) → Elbow (q3) → Wrist Flex (q4) → Wrist Rotation (q5) → Hand
```


| Joint                   | What it does               | Everyday analogy                           |
| ----------------------- | -------------------------- | ------------------------------------------ |
| q1 — Shoulder swing     | Moves arm forward/backward | Scratching your ribs with your inner elbow |
| q2 — Shoulder abduction | Raises arm out to the side | Doing a jumping jack                       |
| q3 — Elbow flexion      | Bends the elbow            | Flexing your bicep                         |
| q4 — Wrist flexion      | Bends the wrist            | Italian chef hand gesture                  |
| q5 — Wrist pronation    | Rotates the wrist          | Turning a doorknob                         |


### Servo Groups → Joints

Your motion scripts use servo group names. Here's how they map to the kinematic joints:


| Motion Script Key     | Servo Index           | Joint                                    |
| --------------------- | --------------------- | ---------------------------------------- |
| `LS[0]` or `RS[0]`    | First shoulder servo  | q1 — shoulder swing                      |
| `LS[1]` or `RS[1]`    | Second shoulder servo | q2 — shoulder abduction                  |
| `LE[0]` or `RE[0]`    | Elbow servo           | q3 — elbow flexion                       |
| `LW[0]` or `RW[0]`    | First wrist servo     | q4 — wrist flexion                       |
| `LW[1]` or `RW[1]`    | Second wrist servo    | q5 — wrist pronation                     |
| `L` or `R` (5 servos) | Finger servos         | Not modeled in 3D — shown as text labels |


### Servo-to-Radian Conversion

Servo values in motion scripts are integers 0–180. The FK math needs radians.

**Current default:**

```
joint_radians = (servo_degrees - 90) * (π / 180)
```

So servo 90° = 0 radians (neutral), servo 0° = -90°, servo 180° = +90°.

> ⚠️ **This default needs calibration.** See [Calibration](#calibration-action-items) below.

---

## Evaluation Checks

When you run `evaluate`, each sign is checked against these rules:


| Check                     | Severity | What it catches                                                    |
| ------------------------- | -------- | ------------------------------------------------------------------ |
| **Servo range**           | FAIL     | Any servo value below 0 or above 180                               |
| **Joint limits**          | FAIL     | Joint angle outside the physically possible range                  |
| **Timing**                | FAIL     | Keyframe times not increasing, or don't match duration             |
| **Angular velocity**      | WARN     | Joint moving faster than 500°/sec (servo can't physically do this) |
| **Duration**              | WARN     | Sign shorter than 0.3s or longer than 5.0s                         |
| **Keyframe completeness** | WARN     | First keyframe has no servo data at all                            |


A sign **passes** if it has zero FAIL-level issues. Warnings are flagged but don't fail the sign.

### Comparison Metrics (for AI evaluation)

When comparing AI-generated signs to reference signs:


| Metric                        | What it measures                                                                                                             |
| ----------------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| **Joint angle MAE**           | Average difference in radians across all joints and keyframes. This is the main "joint tracking error" metric for the paper. |
| **Duration difference**       | How much the sign lengths differ (seconds)                                                                                   |
| **Keyframe count difference** | How many more/fewer keyframes the AI version has                                                                             |
| **Arm agreement**             | Whether both versions use the same arm(s)                                                                                    |


---

## Input Formats

### Sign JSON Format

The tool reads the same JSON format used by the ASL Robot database. Signs can be provided as an array:

```json
[
  {
    "token": "HELLO",
    "type": "DYNAMIC",
    "duration": 2.0,
    "keyframes": [
      {
        "time": 0.0,
        "RS": [90, 45],
        "RE": [120],
        "RW": [90, 90],
        "R": [180, 0, 0, 0, 0]
      },
      {
        "time": 1.0,
        "RS": [90, 90],
        "RE": [90],
        "R": [180, 20, 20, 20, 20]
      },
      {
        "time": 2.0,
        "RS": [90, 45],
        "RE": [120],
        "RW": [90, 90],
        "R": [180, 0, 0, 0, 0]
      }
    ]
  }
]
```

**Key rules:**

- `token`: Sign name (e.g., "HELLO", "THANK-YOU")
- `type`: "STATIC" (one pose) or "DYNAMIC" (multiple keyframes)
- `duration`: Total time in seconds
- `keyframes`: Array of time-stamped servo snapshots
- If a servo group is **missing** from a keyframe, it holds its last value
- Servo groups: `L`/`R` (5 finger servos), `LS`/`RS` (2 shoulder), `LE`/`RE` (1 elbow), `LW`/`RW` (2 wrist)

### AI Model Output

Professor Lin's inference script should output the **exact same JSON format** above. The `compare` command loads it via `--ai-input` and tags it internally as AI-generated for reporting.

### MongoDB

When using `--source mongodb`, the tool reads `MONGODB_URI` and `MONGODB_DB_NAME` from the project's `.env` file (same config the main ASL Robot app uses). No additional setup needed.

---

## File Structure

```
src/fk_tool/
├── __init__.py          # Package marker
├── __main__.py          # python -m src.fk_tool entry point
├── cli.py               # Command-line interface (evaluate, visualize, compare)
├── config.py            # ⚙️  ALL physical constants and calibration live here
├── models.py            # Data structures (ParsedSign, SignEvaluation, etc.)
├── fk_engine.py         # Forward kinematics math (numpy matrix chain)
├── servo_mapper.py      # Servo degrees ↔ joint radians conversion
├── sign_parser.py       # Reads raw sign JSON, normalizes keyframes
├── loaders.py           # File and database loading
├── evaluator.py         # Physical plausibility checks + AI comparison
├── visualizer.py        # 3D matplotlib plotting and animation
├── report.py            # Console, CSV, and HTML report generation
└── tests/
    ├── test_smoke.py        # Core engine tests (9)
    ├── test_evaluator.py    # Evaluation logic tests (6)
    └── test_compare.py      # AI comparison tests (7)
```

**22 tests total.** Run them with:

```bash
python -m pytest src/fk_tool/tests/ -v
```

---

## Calibration (Action Items)

The tool works today for evaluation, batch testing, and relative motion visualization. However, for the 3D visualizations to accurately match the physical robot's poses, these values need to be measured and updated in `src/fk_tool/config.py`:


| #   | What to measure                                                                                 | Where to update                                | Current default         |
| --- | ----------------------------------------------------------------------------------------------- | ---------------------------------------------- | ----------------------- |
| 1   | **Neutral servo position** per joint — what servo angle puts each joint at its "zero" position? | `JOINT_CALIBRATION[joint].neutral_servo_deg`   | 90° for all joints      |
| 2   | **Joint direction** — does increasing the servo angle increase or decrease the joint angle?     | `JOINT_CALIBRATION[joint].scale`               | 1.0 (positive) for all  |
| 3   | **Mechanical limits** — what's the actual range of motion for each joint?                       | `JOINT_CALIBRATION[joint].min_rad` / `max_rad` | ±90° for most joints    |
| 4   | **Right arm shoulder mirroring** — confirm q2 negation direction                                | `get_joint_positions_dual()` in `fk_engine.py` | Negate q2 for right arm |


**How to update:** Edit `config.py`, change the numbers, run the tests (`python -m pytest src/fk_tool/tests/ -v`). No other files need to change.

---

## For Professor Lin — AI Model Testing Workflow

1. Export your model's output as a JSON file in the sign format shown above
2. Run comparison against the database:
  ```bash
   python -m src.fk_tool compare --ai-input your_output.json --ref-source mongodb --report results.html
  ```
3. Open `results.html` in a browser — sortable table showing per-sign MAE, pass/fail, and accuracy ranking
4. The **Joint Angle MAE** column is the "joint tracking error" metric for the paper

## For Professor LaMack — Calibration Workflow

1. For each joint on the physical robot, find the servo value that puts it at neutral (0°)
2. Check if increasing the servo value moves the joint in the positive direction per the MATLAB convention
3. Measure the physical range of motion limits
4. Update `src/fk_tool/config.py` with the measured values
5. Run `python -m src.fk_tool visualize --input src/signs/signs_to_seed.json --token HELLO --save test.png` and visually confirm the pose matches expectations

## For Testing with ASL Club

1. Generate evaluation report:
  ```bash
   python -m src.fk_tool evaluate --source mongodb --report all_signs_eval.html
  ```
2. Generate animated GIFs of signs selected for human evaluation:
  ```bash
   python -m src.fk_tool visualize --source mongodb --token HELLO --animate --save signs/hello.gif
   python -m src.fk_tool visualize --source mongodb --token THANK-YOU --animate --save signs/thankyou.gif
  ```
3. Use the GIFs alongside the physical robot demonstrations for side-by-side comparison

---

## Troubleshooting

**"No module named src.fk_tool"**
Run from the ASL-Robot project root directory. The command is `python -m src.fk_tool`, not `python src/fk_tool`.

**"pymongo is required for MongoDB loading"**
Install it: `pip install pymongo`. Only needed if you use `--source mongodb`.

**"MongoDB URI not found in .env"**
Create a `.env` file in the project root with `MONGODB_URI=your_connection_string` and `MONGODB_DB_NAME=ASLSignsDB`.

**Matplotlib window doesn't open**
If running over SSH or in a headless environment, use `--save` to write to a file instead of opening an interactive window.

**Tests fail after changing config.py**
Some tests verify specific values (like neutral servo = 0 radians). After calibration, you may need to update the expected values in `test_smoke.py`.