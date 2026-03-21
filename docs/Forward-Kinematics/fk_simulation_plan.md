# ASL Robot — FK Simulation & Evaluation Tool

## Engineering Plan

---

## 1. Purpose & Goals

This Python tool replaces Professor LaMack's MATLAB `PlotRobLinks` script with a full-featured,
batch-capable simulation and evaluation pipeline. It serves three core use cases:

**A. Sign Validation** — Verify that motion scripts in MongoDB are physically plausible
before deploying to hardware (joint limits, reachability, timing).

**B. AI Model Evaluation** — Batch-test Professor Lin's AI-generated motion scripts
against the same physical constraints, producing quantitative metrics for the paper.

**C. Visual Demonstration** — Generate 3D animated visualizations of signs for
presentations, the paper, and human evaluation prep.

---

## 2. Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     CLI Entry Point                         │
│         (argparse: mode, input source, options)             │
└────────────┬───────────────────────────────┬────────────────┘
             │                               │
      ┌──────▼──────┐                ┌───────▼───────┐
      │  JSON File   │                │   MongoDB     │
      │  Loader      │                │   Loader      │
      └──────┬──────┘                └───────┬───────┘
             │                               │
             └───────────┬───────────────────┘
                         │
                         ▼
              ┌─────────────────────┐
              │    Sign Parser      │
              │  (normalize schema, │
              │   resolve holds,    │
              │   interpolate)      │
              └──────────┬──────────┘
                         │
              ┌──────────▼──────────┐
              │  Servo-to-Joint     │
              │  Mapper             │
              │  (configurable,     │
              │   per-joint calib)  │
              └──────────┬──────────┘
                         │
          ┌──────────────┼──────────────┐
          │              │              │
   ┌──────▼──────┐ ┌────▼─────┐ ┌─────▼──────┐
   │  FK Engine  │ │Evaluator │ │ Visualizer │
   │  (numpy)    │ │(metrics) │ │(matplotlib)│
   └──────┬──────┘ └────┬─────┘ └─────┬──────┘
          │              │              │
          └──────────────┼──────────────┘
                         │
              ┌──────────▼──────────┐
              │   Report Generator  │
              │  (CSV, JSON, HTML   │
              │   summary)          │
              └─────────────────────┘
```

---

## 3. Module Breakdown

### 3.1 `config.py` — Robot Configuration

Centralizes all physical parameters and calibration constants. This is the single
file Professor LaMack's team or future students need to edit when mechanical specs change.

```python
# --- Link Lengths (inches, matching MATLAB) ---
L_JOINT12  = 1.5    # shoulder offset
L_UPPER    = 15.0   # upper arm
L_FORE     = 10.0   # forearm
L_WRIST    = 1.5    # wrist to hand

# --- Torso Bounding Volume (for self-collision) ---
TORSO_HALF_WIDTH  = 5.0   # inches, X direction
TORSO_HALF_DEPTH  = 2.0   # inches, Y direction
TORSO_HEIGHT      = 30.0  # inches, Z direction (shoulder at Z=0, torso extends downward)

# --- Shoulder Offsets from Body Center ---
# Left shoulder at (-offset, 0, 0), Right at (+offset, 0, 0)
SHOULDER_X_OFFSET = 7.0   # inches from centerline to each shoulder

# --- Servo-to-Joint Mapping ---
# Each entry: (servo_neutral_deg, joint_zero_deg, scale_factor, min_rad, max_rad)
#
# Formula: joint_rad = (servo_deg - servo_neutral) * scale * (pi/180)
#
# DEFAULT ASSUMPTION: 90° servo = 0 rad joint angle
# ACTION ITEM: Confirm with Professor LaMack / engineering team
#
JOINT_CALIBRATION = {
    # joint_name: (servo_neutral_deg, scale_factor, min_rad, max_rad)
    "shoulder_swing":     (90,  1.0, -1.57,  1.57),  # q1: LS[0]/RS[0]
    "shoulder_abduction": (90,  1.0, -1.57,  1.57),  # q2: LS[1]/RS[1]
    "elbow_flexion":      (90,  1.0,  0.0,   2.36),  # q3: LE/RE  (0 to ~135°)
    "wrist_flexion":      (90,  1.0, -1.22,  1.22),  # q4: LW[0]/RW[0]
    "wrist_pronation":    (90,  1.0, -1.57,  1.57),  # q5: LW[1]/RW[1]
}

# --- Servo Group to Joint Mapping ---
# Maps sign schema servo groups to kinematic joint indices
SERVO_TO_JOINT = {
    # Left arm
    "LS": [("shoulder_swing", 0), ("shoulder_abduction", 1)],  # LS[0]→q1, LS[1]→q2
    "LE": [("elbow_flexion", 0)],                               # LE[0]→q3
    "LW": [("wrist_flexion", 0), ("wrist_pronation", 1)],       # LW[0]→q4, LW[1]→q5
    # Right arm
    "RS": [("shoulder_swing", 0), ("shoulder_abduction", 1)],
    "RE": [("elbow_flexion", 0)],
    "RW": [("wrist_flexion", 0), ("wrist_pronation", 1)],
}

# --- Finger servo groups (not modeled in FK, stored as metadata) ---
FINGER_GROUPS = ["L", "R"]
```

**Why this matters:** When Professor LaMack confirms the real servo-to-radian mapping,
you change numbers in ONE file. Every other module reads from here.

---

### 3.2 `sign_parser.py` — Sign Data Normalization

Reads raw sign data (from JSON or MongoDB) and produces a clean, uniform internal
representation ready for the FK engine.

**Responsibilities:**

1. **Schema validation** — Verify required fields exist (`token`, `type`, `duration`, `keyframes`)
2. **Keyframe normalization** — Ensure `keyframes` is always a list (handles dict edge case from some DB paths, per Sprint 6 notes)
3. **Hold resolution** — If a servo group is omitted from a keyframe, carry forward the last known value (matching how the Arduino firmware behaves)
4. **Default filling** — For the very first keyframe, any missing servo groups default to the neutral/rest position (all 90°)
5. **Time sorting** — Ensure keyframes are sorted by `time` field
6. **Arm detection** — Determine which arm(s) the sign uses (left-only, right-only, both) based on which servo groups appear

**Internal data structure (output):**

```python
@dataclass
class ParsedSign:
    token: str
    sign_type: str                    # "STATIC" or "DYNAMIC"
    duration: float                   # seconds
    arm: str                          # "left", "right", "both"
    keyframes: list[ParsedKeyframe]   # time-sorted, fully resolved
    finger_data: dict                 # L/R finger states per keyframe (for display only)
    raw: dict                         # original document for reference

@dataclass
class ParsedKeyframe:
    time: float
    left_servos: dict[str, list[int]]   # {"LS": [90,90], "LE": [90], "LW": [90,90]}
    right_servos: dict[str, list[int]]  # {"RS": [90,90], "RE": [90], "RW": [90,90]}
    left_fingers: list[int] | None      # L group (5 values) or None
    right_fingers: list[int] | None     # R group (5 values) or None
```

---

### 3.3 `fk_engine.py` — Forward Kinematics (Direct MATLAB Port)

This is the mathematical core. A pure numpy port of Professor LaMack's transformation  
matrices, producing 3D joint positions for one arm. BASED ON PlotRobotLinks file. LOGIC SHOULD REMAIN IDENTICAL.

**MATLAB → Python mapping (line by line):**

```
MATLAB T01 → T_shoulder_swing:     Rotation about X by q1
MATLAB T12 → T_shoulder_abduction: Rotation about Y by q2, translate X by L_JOINT12
MATLAB T23 → T_elbow_flexion:      Rotation about X by q3, translate Z by -L_UPPER
MATLAB T34 → T_wrist_flexion:      Rotation about X by q4, translate Z by -L_FORE
MATLAB T45 → T_wrist_pronation:    Rotation about Z by q5, translate Z by -L_WRIST
```

**Key functions:**

```python
def compute_transforms(q: np.ndarray) -> list[np.ndarray]:
    """
    Given 5 joint angles (radians), return list of 6 homogeneous
    transforms: [T_base, T_shoulder1, T_shoulder2, T_elbow, T_wrist, T_hand]
    Each is a 4x4 matrix in world frame.
    """

def get_joint_positions(q: np.ndarray) -> np.ndarray:
    """
    Given 5 joint angles, return 6x3 array of (x,y,z) positions
    for: [shoulder_base, shoulder_joint, elbow, wrist, hand_tip]
    """

def get_joint_positions_dual(
    q_left: np.ndarray,
    q_right: np.ndarray,
    mirror_right: bool = True
) -> tuple[np.ndarray, np.ndarray]:
    """
    Compute both arms. Right arm is mirrored about X axis
    (shoulder offset positive vs negative).
    Returns (left_positions, right_positions).
    """
```

**Critical detail — right arm mirroring:**
The MATLAB script models one arm. For the right arm, we mirror the shoulder
offset (negate X) and potentially flip q2 sign (abduction goes the other way).
This needs validation with Professor LaMack but the config makes it easy to adjust.

---

### 3.4 `servo_mapper.py` — Servo Angles → Joint Angles

Converts integer servo values (0-180°) from motion scripts into the radians
the FK engine expects, using the calibration table from `config.py`.

```python
def servos_to_joint_angles(
    servo_groups: dict[str, list[int]],
    side: str  # "left" or "right"
) -> np.ndarray:
    """
    Takes servo group dict (e.g. {"LS": [90,90], "LE": [90], "LW": [90,90]})
    Returns: np.array of 5 joint angles in radians [q1, q2, q3, q4, q5]

    Uses JOINT_CALIBRATION from config:
        joint_rad = (servo_deg - neutral_deg) * scale * (pi/180)
    """

def joint_angles_to_servos(
    q: np.ndarray,
    side: str
) -> dict[str, list[int]]:
    """
    Inverse: joint angles back to servo values.
    Useful for generating corrected motion scripts.
    """
```

---

### 3.5 `evaluator.py` — Quantitative Metrics Engine

Runs a battery of checks on each sign and produces a structured evaluation result.

**Metrics computed per sign:**


| Metric                  | Description                                                          | Pass/Fail Criteria    |
| ----------------------- | -------------------------------------------------------------------- | --------------------- |
| Joint Limit Violations  | Any joint angle outside calibrated min/max                           | FAIL if any violation |
| Servo Range Violations  | Any servo value < 0 or > 180                                         | FAIL if any violation |
| Angular Velocity        | Max degrees/sec between consecutive keyframes per joint              | WARN if > threshold   |
| Self-Collision          | Does any arm link segment intersect the torso bounding box           | FAIL if collision     |
| Reachability            | Can the FK chain reach the commanded position without hyperextension | FAIL if unreachable   |
| Timing Sanity           | Are keyframe times monotonically increasing, within [0, duration]    | FAIL if violated      |
| Keyframe Completeness   | Are all required servo groups present in at least the first keyframe | WARN if missing       |
| Duration Reasonableness | Is duration within expected range (0.3s - 5.0s for typical signs)    | WARN if outside       |
| Smoothness Score        | Jerk (rate of change of acceleration) across keyframes               | INFO (0.0-1.0 score)  |


**Output structure:**

```python
@dataclass
class SignEvaluation:
    token: str
    passed: bool                        # True if no FAIL-level issues
    errors: list[EvalIssue]             # FAIL-level
    warnings: list[EvalIssue]           # WARN-level
    info: list[EvalIssue]               # INFO-level
    metrics: dict[str, float]           # Numeric scores
    joint_angles_over_time: list        # For plotting/debugging
    positions_over_time: list           # FK output per keyframe

@dataclass
class EvalIssue:
    level: str          # "FAIL", "WARN", "INFO"
    metric: str         # e.g. "joint_limit_violation"
    message: str        # Human-readable description
    keyframe_idx: int   # Which keyframe triggered this
    joint: str          # Which joint (if applicable)
    value: float        # The offending value
    limit: float        # The limit it exceeded
```

---

### 3.6 `visualizer.py` — 3D Animated Plots

Generates matplotlib 3D animations of signs, replicating and extending what the
MATLAB script does.

**Visualization modes:**

1. **Single keyframe** — Static 3D plot of one pose (like the MATLAB output)
2. **Animated sign** — `FuncAnimation` stepping through keyframes with interpolation
3. **Side-by-side comparison** — Two signs overlaid (e.g., AI-generated vs database reference)
4. **Batch thumbnails** — Grid of static first-keyframe poses for quick visual scan

**Plot elements:**

- Stick-figure arm links (colored by segment: shoulder=blue, upper arm=green, forearm=orange, wrist=red)
- Joint markers (dots at each joint position)
- Torso bounding box (translucent gray, for collision reference)
- Ghost trail of previous keyframe poses (faded)
- Token name + keyframe index as title
- Finger state as a text annotation (since fingers aren't in the kinematic model)
- Dual arm support with shoulder offsets

**Output formats:**

- Interactive matplotlib window (for development)
- `.png` per keyframe (for reports/paper)
- `.gif` animated (for presentations)
- `.mp4` animated (for demonstration videos)

**Key function signatures:**

```python
def plot_single_pose(q_left, q_right, title="", save_path=None): ...
def animate_sign(parsed_sign: ParsedSign, fps=30, save_path=None): ...
def compare_signs(sign_a: ParsedSign, sign_b: ParsedSign, save_path=None): ...
def batch_thumbnails(signs: list[ParsedSign], cols=5, save_path=None): ...
```

---

### 3.7 `loaders.py` — Data Input Sources

**JSON File Loader:**

```python
def load_from_json(filepath: str) -> list[dict]:
    """
    Load signs from a JSON file.
    Supports both formats:
      - Array of sign objects: [{"token": "HELLO", ...}, ...]
      - Object keyed by token: {"HELLO": {...}, "THANK-YOU": {...}}
    Returns list of raw sign dicts.
    """
```

**MongoDB Loader:**

```python
def load_from_mongodb(
    uri: str = None,         # defaults to .env MONGODB_URI
    db_name: str = None,     # defaults to .env MONGODB_DB_NAME
    tokens: list[str] = None # filter to specific tokens, or None for ALL
) -> list[dict]:
    """
    Pull signs directly from MongoDB.
    Uses same connection config as the main ASL Robot app.
    """
```

**Professor Lin AI Output Loader:**

```python
def load_from_ai_output(filepath: str) -> list[dict]:
    """
    Load AI-generated motion scripts. Same schema as standard signs.
    Wraps load_from_json but adds a metadata tag marking these as AI-generated
    for comparison reporting.
    """
```

---

### 3.8 `report.py` — Batch Reporting

After evaluating N signs, produces summary reports.

**Output formats:**

1. **Console summary** — Quick pass/fail counts, worst offenders
2. **CSV** — One row per sign, columns for each metric (for spreadsheet analysis)
3. **JSON** — Full structured evaluation results (machine-readable)
4. **HTML report** — Visual summary with embedded pose thumbnails and color-coded pass/fail (for sharing with professors/team)

**Report contents:**

- Total signs evaluated
- Pass/fail/warn counts
- Most common failure modes
- Per-sign detail table (sortable by any metric)
- Distribution histograms (joint angle ranges, velocities, durations)
- List of signs that need attention, ranked by severity

---

### 3.9 `cli.py` — Command Line Interface

The main entry point. Uses argparse for clean, scriptable invocation.

**Usage examples:**

```bash
# Evaluate a single sign from JSON
python -m fk_tool evaluate --input sign.json --token HELLO

# Batch evaluate all signs from a JSON file
python -m fk_tool evaluate --input signs_to_seed.json --report results.csv

# Batch evaluate all signs in MongoDB
python -m fk_tool evaluate --source mongodb --report results.csv

# Evaluate AI-generated signs against database reference
python -m fk_tool compare --ai-input ai_output.json --db-source mongodb --report comparison.html

# Visualize a single sign
python -m fk_tool visualize --input signs.json --token HELLO --animate --save hello.gif

# Batch thumbnails of all signs
python -m fk_tool visualize --input signs.json --thumbnails --save overview.png

# Quick single-pose test (raw joint angles in radians)
python -m fk_tool pose --angles 0.0 0.5 1.0 0.3 0.0
```

**Subcommands:**


| Command     | Description                                 |
| ----------- | ------------------------------------------- |
| `evaluate`  | Run metrics on signs, produce report        |
| `visualize` | Generate plots/animations                   |
| `compare`   | Side-by-side AI vs reference evaluation     |
| `pose`      | Quick single-pose FK visualization          |
| `export`    | Export corrected/clamped signs back to JSON |


---

## 4. File/Folder Structure

```
fk_tool/
├── __main__.py          # Entry point (python -m fk_tool)
├── cli.py               # Argument parsing and command dispatch
├── config.py            # Robot dimensions, calibration, joint limits
├── sign_parser.py       # Schema validation, keyframe normalization
├── servo_mapper.py      # Servo degrees ↔ joint radians conversion
├── fk_engine.py         # Forward kinematics (numpy port of MATLAB)
├── evaluator.py         # Quantitative metrics and checks
├── visualizer.py        # Matplotlib 3D plotting and animation
├── loaders.py           # JSON file + MongoDB data loading
├── report.py            # CSV/JSON/HTML report generation
├── models.py            # Dataclasses (ParsedSign, SignEvaluation, etc.)
└── tests/
    ├── test_fk_engine.py      # Validate FK matches MATLAB output
    ├── test_sign_parser.py    # Schema edge cases
    ├── test_servo_mapper.py   # Round-trip conversion tests
    └── test_evaluator.py      # Known-good and known-bad signs
```

---

## 5. Implementation Order (Suggested Build Phases)

### Phase 1: Core Engine (foundation — everything depends on this)

1. `config.py` — constants and calibration table
2. `models.py` — dataclasses
3. `fk_engine.py` — numpy FK, verified against MATLAB output for known angles
4. `servo_mapper.py` — conversion layer
5. `tests/test_fk_engine.py` — CRITICAL: compute a few poses in MATLAB, compare numerically

**Deliverable:** Given servo angles, produce correct 3D joint positions.
**Validation:** Run MATLAB with q = [0, 0.5, 1.0, 0.3, 0] and Python with same — positions must match within 1e-6.

### Phase 2: Sign Processing

1. `sign_parser.py` — normalize sign data, resolve holds
2. `loaders.py` — JSON file loading (MongoDB comes later)
3. Quick integration test: load `signs_to_seed.json`, parse all signs, confirm no crashes

**Deliverable:** Load any sign from JSON, get clean keyframe sequence with all servo groups resolved.

### Phase 3: Visualization

1. `visualizer.py` — single pose, then animated sign
2. Test with known signs from the database: visually confirm arm looks right

**Deliverable:** Animated 3D stick figure performing a sign. Can show to Professor LaMack for visual validation of the FK port.

### Phase 4: Evaluation

1. `evaluator.py` — all metric checks
2. `report.py` — CSV and console output
3. `cli.py` — wire up `evaluate` and `visualize` commands

**Deliverable:** Run `python -m fk_tool evaluate --input signs_to_seed.json` and get a full pass/fail report.

### Phase 5: Batch & MongoDB

1. `loaders.py` — add MongoDB loader
2. Batch mode: evaluate all signs from DB, generate summary report
3. HTML report with thumbnails

**Deliverable:** One command to evaluate every sign in the database.

### Phase 6: AI Comparison

1. `compare` command — load AI output + DB reference, evaluate both, diff metrics
2. Comparison HTML report with side-by-side visuals

**Deliverable:** Feed Professor Lin's AI output, get quantitative evaluation for the paper.

---

## 6. Key Technical Decisions & Assumptions

### 6.1 Servo Mapping (ACTION ITEM)

**Current assumption:**

- Servo 90° = joint angle 0 rad (neutral position)
- Servo 0° = -π/2 rad, Servo 180° = +π/2 rad
- Linear mapping, scale factor 1.0 for all joints

**What to confirm with Professor LaMack / engineering team:**

- Is 90° truly neutral for all servos?
- Are any joints inverted (servo increase = joint decrease)?
- What are the actual mechanical limits per joint? (The servos go 0-180° but the physical arm may have smaller range)
- Are the elbow and wrist offsets (the -90° mentioned in the MATLAB comment for T34) already accounted for in the servo values, or do we need to add them?

**Impact if wrong:** Signs will look correct in relative motion but be offset or flipped. Easy to fix in config.py once we have ground truth.

### 6.2 Right Arm Mirroring

The MATLAB script models one arm. For dual-arm signs we need to handle the right arm.

**Approach:**

- Right shoulder is offset at +X (left at -X)
- Right arm q2 (abduction) sign may need to be negated (abduction goes outward for both arms, but "outward" is opposite directions)
- The FK matrices are identical except for the shoulder base position and potentially the q2 sign

**Decision:** Make mirroring configurable in config.py. Default to negating q2 for right arm. Verify visually with a known two-handed sign.

### 6.3 Keyframe Interpolation

The Arduino firmware moves servos smoothly between keyframes using VarSpeedServo.
For simulation accuracy, we should interpolate between keyframes rather than jumping.

**Approach:** Linear interpolation between keyframes at a configurable FPS (default 30).
This gives smooth animation and allows velocity/acceleration computation for metrics.

### 6.4 Finger Display

The FK model has 5 DOF (shoulder through wrist). Fingers (L/R groups, 5 servos each) are NOT
in the kinematic chain — there's no finger geometry in the MATLAB model.

**Approach:** Display finger states as text annotation or simple indicator bars alongside
the 3D arm plot. Don't try to model finger geometry (would require a separate hand model).

### 6.5 Dependencies

Keep it minimal and standard:

- `numpy` — matrix math (already in most Python environments)
- `matplotlib` — 3D plotting and animation
- `pymongo` — MongoDB access (already in project requirements)
- `python-dotenv` — env config (already in project requirements)

No exotic dependencies. This runs anywhere the main ASL Robot project runs.

---

## 7. Testing Strategy

### Unit Tests

- FK engine: compare output against MATLAB for 5+ known angle sets
- Servo mapper: round-trip (servo→radian→servo) preserves values
- Sign parser: handles missing groups, unsorted keyframes, dict-format keyframes

### Integration Tests

- Load `signs_to_seed.json`, evaluate all, expect 0 crashes
- Load a known-good sign, expect all metrics pass
- Load a deliberately broken sign (servo=999), expect correct FAIL

### Visual Validation

- Generate plots for 5 known signs, have Professor LaMack confirm poses look right
- This is THE critical validation step for the FK port

---

## 8. Deliverables for the Paper

This tool directly produces what you need for the "Deployment and Evaluation" section:


| Paper Need                                  | Tool Output                                        |
| ------------------------------------------- | -------------------------------------------------- |
| Quantitative metrics (joint tracking error) | `evaluate` → CSV with per-sign metrics             |
| Execution success rates                     | `evaluate` → pass/fail percentages                 |
| Physical plausibility validation            | `evaluate` → joint limit + collision checks        |
| Visual demonstrations                       | `visualize` → figures, GIFs for paper/presentation |
| AI model accuracy evaluation                | `compare` → AI vs reference metrics                |
| Testing methodology documentation           | This plan + tool's metric definitions              |


---

## 9. Open Questions / Action Items


| #   | Item                                                          | Owner               | Blocking?                 |
| --- | ------------------------------------------------------------- | ------------------- | ------------------------- |
| 1   | Confirm servo-to-radian mapping with Professor LaMack         | You                 | No (configurable default) |
| 2   | Get sample AI output from Professor Lin to validate format    | You                 | No (same schema agreed)   |
| 3   | Determine exact joint limits for each physical joint          | Engineering team    | No (using safe defaults)  |
| 4   | Right arm mirroring convention — does q2 negate?              | Professor LaMack    | No (configurable)         |
| 5   | Finger display preference — text labels vs mini visualization | Team decision       | No                        |
| 6   | Target sign count for batch evaluation (50-100 per plan)      | You + Professor Lin | No                        |


