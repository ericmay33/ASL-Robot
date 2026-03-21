"""
Robot configuration constants for forward kinematics.

All physical dimensions, joint calibration, and servo-to-joint mappings live here.
Change numbers in this ONE file when mechanical specs change — every other module reads from here.
"""

import math
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Link lengths (inches) — matching Professor LaMack's MATLAB PlotRobotLinks
# ---------------------------------------------------------------------------

SHOULDER_OFFSET_LENGTH: float = 1.5      # T12 translation along X (shoulder joint spacing)
UPPER_ARM_LENGTH: float = 15.0           # T23 translation along -Z (shoulder to elbow)
FOREARM_LENGTH: float = 10.0             # T34 translation along -Z (elbow to wrist)
WRIST_LENGTH: float = 1.5               # T45 translation along -Z (wrist to hand tip)

# ---------------------------------------------------------------------------
# Shoulder offsets from body center (for dual-arm rendering)
# ---------------------------------------------------------------------------

SHOULDER_X_OFFSET: float = 7.0  # inches from centerline to each shoulder


# ---------------------------------------------------------------------------
# Per-joint servo calibration
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class JointCalibration:
    """Calibration parameters for one kinematic joint.

    Attributes:
        neutral_servo_deg: Servo angle (degrees) that corresponds to 0 radians.
        scale: Multiplier applied before degree-to-radian conversion.
               Use -1.0 to invert the joint direction.
        min_rad: Lower mechanical limit in radians.
        max_rad: Upper mechanical limit in radians.
    """
    neutral_servo_deg: float
    scale: float
    min_rad: float
    max_rad: float


# Default calibration: servo 90 deg = 0 rad, linear 1:1, symmetric limits.
# ACTION ITEM: Confirm with Professor LaMack / engineering team.
JOINT_CALIBRATION: dict[str, JointCalibration] = {
    "shoulder_swing":     JointCalibration(neutral_servo_deg=90.0, scale=1.0, min_rad=-math.pi / 2, max_rad=math.pi / 2),
    "shoulder_abduction": JointCalibration(neutral_servo_deg=90.0, scale=1.0, min_rad=-math.pi / 2, max_rad=math.pi / 2),
    "elbow_flexion":      JointCalibration(neutral_servo_deg=90.0, scale=1.0, min_rad=-0.6109,       max_rad=2.356),
    "wrist_flexion":      JointCalibration(neutral_servo_deg=90.0, scale=1.0, min_rad=-math.pi / 2, max_rad=math.pi / 2),
    "wrist_pronation":    JointCalibration(neutral_servo_deg=90.0, scale=1.0, min_rad=-math.pi / 2, max_rad=math.pi / 2),
}

# Ordered list of joint names matching the 5-DOF kinematic chain (q1..q5).
JOINT_NAMES: list[str] = [
    "shoulder_swing",       # q1 — rotation about X
    "shoulder_abduction",   # q2 — rotation about Y
    "elbow_flexion",        # q3 — rotation about X
    "wrist_flexion",        # q4 — rotation about X
    "wrist_pronation",      # q5 — rotation about Z
]

NUM_JOINTS: int = len(JOINT_NAMES)


# ---------------------------------------------------------------------------
# Servo group → kinematic joint mapping
# ---------------------------------------------------------------------------
# Each entry maps a servo-group key (from sign JSON) to a list of
# (joint_name, index_within_group) tuples.

SERVO_GROUP_TO_JOINTS: dict[str, list[tuple[str, int]]] = {
    # Left arm
    "LS": [("shoulder_swing", 0), ("shoulder_abduction", 1)],
    "LE": [("elbow_flexion", 0)],
    "LW": [("wrist_flexion", 0), ("wrist_pronation", 1)],
    # Right arm
    "RS": [("shoulder_swing", 0), ("shoulder_abduction", 1)],
    "RE": [("elbow_flexion", 0)],
    "RW": [("wrist_flexion", 0), ("wrist_pronation", 1)],
}

# Finger servo groups — not part of the FK chain, stored as metadata only.
FINGER_GROUPS: list[str] = ["L", "R"]

# Servo groups belonging to each arm side.
LEFT_ARM_GROUPS: list[str] = ["LS", "LE", "LW"]
RIGHT_ARM_GROUPS: list[str] = ["RS", "RE", "RW"]

# ---------------------------------------------------------------------------
# Default servo positions (degrees) for missing keyframe data
# ---------------------------------------------------------------------------

DEFAULT_SERVO_POSITIONS: dict[str, list[float]] = {
    "LS": [90.0, 90.0],
    "LE": [90.0],
    "LW": [90.0, 90.0],
    "RS": [90.0, 90.0],
    "RE": [90.0],
    "RW": [90.0, 90.0],
    "L":  [90.0, 90.0, 90.0, 90.0, 90.0],
    "R":  [90.0, 90.0, 90.0, 90.0, 90.0],
}

# ---------------------------------------------------------------------------
# Evaluation thresholds
# ---------------------------------------------------------------------------

SERVO_MIN_DEGREES: float = 0.0       # Minimum valid servo angle
SERVO_MAX_DEGREES: float = 180.0     # Maximum valid servo angle

MAX_ANGULAR_VELOCITY_DEG_PER_SEC: float = 500.0  # Physical servo speed limit

MIN_SIGN_DURATION_SEC: float = 0.3   # Shortest reasonable sign
MAX_SIGN_DURATION_SEC: float = 5.0   # Longest reasonable sign

# ---------------------------------------------------------------------------
# Visualization defaults
# ---------------------------------------------------------------------------

AXIS_LIMIT: float = 30.0  # Axis range [-limit, +limit] on all axes (inches)

# Link colors for stick-figure rendering, ordered by segment.
LINK_COLORS: list[str] = ["blue", "blue", "green", "orange", "red"]
JOINT_MARKER_COLOR: str = "black"
JOINT_MARKER_SIZE: float = 6.0
LINK_LINE_WIDTH: float = 2.0
