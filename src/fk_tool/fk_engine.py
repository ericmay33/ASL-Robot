"""
Forward kinematics engine — numpy port of Professor LaMack's MATLAB PlotRobotLinks.

5-DOF kinematic chain per arm using homogeneous 4x4 transformation matrices.
Joint angles q1-q5 in radians are chained to produce 3D joint positions.
"""

import numpy as np

from . import config


# ---------------------------------------------------------------------------
# Individual transformation matrix builders
# ---------------------------------------------------------------------------

def _rotation_x(angle_rad: float) -> np.ndarray:
    """Build a 4x4 homogeneous rotation matrix about the X axis.

    Args:
        angle_rad: Rotation angle in radians.

    Returns:
        4x4 numpy array.
    """
    cos_a = np.cos(angle_rad)
    sin_a = np.sin(angle_rad)
    return np.array([
        [1.0,  0.0,    0.0,   0.0],
        [0.0,  cos_a, -sin_a, 0.0],
        [0.0,  sin_a,  cos_a, 0.0],
        [0.0,  0.0,    0.0,   1.0],
    ])


def _rotation_y(angle_rad: float) -> np.ndarray:
    """Build a 4x4 homogeneous rotation matrix about the Y axis.

    Args:
        angle_rad: Rotation angle in radians.

    Returns:
        4x4 numpy array.
    """
    cos_a = np.cos(angle_rad)
    sin_a = np.sin(angle_rad)
    return np.array([
        [ cos_a, 0.0, sin_a, 0.0],
        [ 0.0,   1.0, 0.0,   0.0],
        [-sin_a, 0.0, cos_a, 0.0],
        [ 0.0,   0.0, 0.0,   1.0],
    ])


def _rotation_z(angle_rad: float) -> np.ndarray:
    """Build a 4x4 homogeneous rotation matrix about the Z axis.

    Args:
        angle_rad: Rotation angle in radians.

    Returns:
        4x4 numpy array.
    """
    cos_a = np.cos(angle_rad)
    sin_a = np.sin(angle_rad)
    return np.array([
        [cos_a, -sin_a, 0.0, 0.0],
        [sin_a,  cos_a, 0.0, 0.0],
        [0.0,    0.0,   1.0, 0.0],
        [0.0,    0.0,   0.0, 1.0],
    ])


def _translation(x: float, y: float, z: float) -> np.ndarray:
    """Build a 4x4 homogeneous translation matrix.

    Args:
        x: Translation along X axis.
        y: Translation along Y axis.
        z: Translation along Z axis.

    Returns:
        4x4 numpy array.
    """
    return np.array([
        [1.0, 0.0, 0.0, x],
        [0.0, 1.0, 0.0, y],
        [0.0, 0.0, 1.0, z],
        [0.0, 0.0, 0.0, 1.0],
    ])


# ---------------------------------------------------------------------------
# Per-joint transform builders (direct MATLAB port)
# ---------------------------------------------------------------------------

def _build_shoulder_swing_transform(shoulder_swing_angle: float) -> np.ndarray:
    """T01: Shoulder swing — rotation about X, no translation.

    Args:
        shoulder_swing_angle: q1 in radians.

    Returns:
        4x4 homogeneous transform.
    """
    return _rotation_x(shoulder_swing_angle)


def _build_shoulder_abduction_transform(shoulder_abduction_angle: float) -> np.ndarray:
    """T12: Shoulder abduction — rotation about Y, translate X by shoulder offset.

    Args:
        shoulder_abduction_angle: q2 in radians.

    Returns:
        4x4 homogeneous transform.
    """
    rotation = _rotation_y(shoulder_abduction_angle)
    rotation[0, 3] = config.SHOULDER_OFFSET_LENGTH
    return rotation


def _build_elbow_flexion_transform(elbow_flexion_angle: float) -> np.ndarray:
    """T23: Elbow flexion — rotation about X, translate Z by -upper_arm_length.

    Args:
        elbow_flexion_angle: q3 in radians.

    Returns:
        4x4 homogeneous transform.
    """
    rotation = _rotation_x(elbow_flexion_angle)
    rotation[2, 3] = -config.UPPER_ARM_LENGTH
    return rotation


def _build_wrist_flexion_transform(wrist_flexion_angle: float) -> np.ndarray:
    """T34: Wrist flexion — rotation about X, translate Z by -forearm_length.

    Args:
        wrist_flexion_angle: q4 in radians.

    Returns:
        4x4 homogeneous transform.
    """
    rotation = _rotation_x(wrist_flexion_angle)
    rotation[2, 3] = -config.FOREARM_LENGTH
    return rotation


def _build_wrist_pronation_transform(wrist_pronation_angle: float) -> np.ndarray:
    """T45: Wrist pronation — rotation about Z, translate Z by -wrist_length.

    Args:
        wrist_pronation_angle: q5 in radians.

    Returns:
        4x4 homogeneous transform.
    """
    rotation = _rotation_z(wrist_pronation_angle)
    rotation[2, 3] = -config.WRIST_LENGTH
    return rotation


# Ordered list of transform builders matching joint order q1..q5.
_TRANSFORM_BUILDERS = [
    _build_shoulder_swing_transform,
    _build_shoulder_abduction_transform,
    _build_elbow_flexion_transform,
    _build_wrist_flexion_transform,
    _build_wrist_pronation_transform,
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_transforms(joint_angles: np.ndarray) -> list[np.ndarray]:
    """Compute cumulative world-frame transforms for each joint in the chain.

    Chains T01 @ T12 @ T23 @ T34 @ T45 and returns the cumulative transform
    at each stage, starting from the identity (base frame).

    Args:
        joint_angles: Array of 5 joint angles in radians [q1, q2, q3, q4, q5].

    Returns:
        List of 6 cumulative 4x4 transforms:
        [T_base, T_after_shoulder_swing, T_after_shoulder_abduction,
         T_after_elbow, T_after_wrist_flexion, T_after_wrist_pronation].
    """
    if len(joint_angles) != config.NUM_JOINTS:
        raise ValueError(
            f"Expected {config.NUM_JOINTS} joint angles, got {len(joint_angles)}"
        )

    cumulative_transforms = [np.eye(4)]
    current_transform = np.eye(4)

    for index in range(config.NUM_JOINTS):
        local_transform = _TRANSFORM_BUILDERS[index](joint_angles[index])
        current_transform = current_transform @ local_transform
        cumulative_transforms.append(current_transform.copy())

    return cumulative_transforms


def get_joint_positions(joint_angles: np.ndarray) -> np.ndarray:
    """Compute 3D positions of all joints in the kinematic chain.

    Args:
        joint_angles: Array of 5 joint angles in radians [q1, q2, q3, q4, q5].

    Returns:
        6x3 numpy array of (x, y, z) positions for:
        [shoulder_base, post_swing, post_abduction, elbow, wrist, hand_tip].
    """
    cumulative_transforms = compute_transforms(joint_angles)
    positions = np.array([transform[0:3, 3] for transform in cumulative_transforms])
    return positions


def get_joint_positions_dual(
    left_joint_angles: np.ndarray,
    right_joint_angles: np.ndarray,
    mirror_right: bool = True,
) -> tuple[np.ndarray, np.ndarray]:
    """Compute joint positions for both arms with shoulder offsets.

    Left shoulder is offset to -X, right shoulder to +X.
    When mirror_right is True, the right arm's shoulder abduction angle (q2)
    is negated so that abduction goes outward on both sides.

    Args:
        left_joint_angles: 5-element array of left arm joint angles (radians).
        right_joint_angles: 5-element array of right arm joint angles (radians).
        mirror_right: If True, negate q2 for the right arm.

    Returns:
        Tuple of (left_positions, right_positions), each a 6x3 array.
    """
    left_angles_adjusted = left_joint_angles.copy()
    if mirror_right:
        left_angles_adjusted[1] = -left_angles_adjusted[1]

    left_positions = get_joint_positions(left_angles_adjusted)
    left_positions[:, 0] = -left_positions[:, 0] - config.SHOULDER_X_OFFSET

    right_positions = get_joint_positions(right_joint_angles)
    right_positions[:, 0] += config.SHOULDER_X_OFFSET

    return left_positions, right_positions
