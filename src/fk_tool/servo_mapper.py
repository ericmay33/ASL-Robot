"""
Servo-to-joint angle conversion.

Converts integer servo values (0-180 degrees) from motion scripts into radians
for the FK engine, and vice versa. Uses calibration from config.py.
"""

import math

import numpy as np

from . import config


def servo_degrees_to_radians(servo_deg: float, joint_name: str, side: str) -> float:
    """Convert a single servo angle to a joint angle in radians.

    Formula: joint_rad = (servo_deg - neutral) * scale * (pi / 180)

    Args:
        servo_deg: Servo position in degrees (typically 0-180).
        joint_name: Name of the joint (must be a key in the joint calibration map).
        side: "left" or "right" — selects the appropriate calibration values.

    Returns:
        Joint angle in radians.
    """
    calibration = config.joint_calibration_for_side(side)[joint_name]
    offset_degrees = (servo_deg - calibration.neutral_servo_deg) * calibration.scale
    return offset_degrees * (math.pi / 180.0)


def radians_to_servo_degrees(joint_rad: float, joint_name: str, side: str) -> float:
    """Convert a joint angle in radians back to servo degrees.

    Inverse of servo_degrees_to_radians.

    Args:
        joint_rad: Joint angle in radians.
        joint_name: Name of the joint (must be a key in the joint calibration map).
        side: "left" or "right" — selects the appropriate calibration values.

    Returns:
        Servo position in degrees.
    """
    calibration = config.joint_calibration_for_side(side)[joint_name]
    offset_degrees = joint_rad * (180.0 / math.pi)
    return (offset_degrees / calibration.scale) + calibration.neutral_servo_deg


def servos_to_joint_angles(
    servo_groups: dict[str, list[float]],
    side: str,
) -> np.ndarray:
    """Convert servo group dict to an array of 5 joint angles in radians.

    Maps servo groups (e.g. LS, LE, LW) to the ordered joint angle vector
    [q1, q2, q3, q4, q5] used by the FK engine.

    Args:
        servo_groups: Dict with keys like "LS"/"LE"/"LW" (or RS/RE/RW),
                      values are lists of servo angles in degrees.
        side: "left" or "right" — determines which group prefix to use.

    Returns:
        Numpy array of 5 joint angles in radians.
    """
    joint_angles = np.zeros(config.NUM_JOINTS)

    if side == "left":
        group_keys = config.LEFT_ARM_GROUPS
    elif side == "right":
        group_keys = config.RIGHT_ARM_GROUPS
    else:
        raise ValueError(f"side must be 'left' or 'right', got '{side}'")

    for group_key in group_keys:
        if group_key not in servo_groups:
            continue
        mappings = config.SERVO_GROUP_TO_JOINTS[group_key]
        servo_values = servo_groups[group_key]
        for joint_name, servo_index in mappings:
            joint_index = config.JOINT_NAMES.index(joint_name)
            joint_angles[joint_index] = servo_degrees_to_radians(
                servo_values[servo_index], joint_name, side
            )

    return joint_angles


def joint_angles_to_servos(
    joint_angles: np.ndarray,
    side: str,
) -> dict[str, list[float]]:
    """Convert joint angles back to servo group dict.

    Inverse of servos_to_joint_angles. Useful for generating corrected motion scripts.

    Args:
        joint_angles: Numpy array of 5 joint angles in radians.
        side: "left" or "right".

    Returns:
        Dict mapping group keys (e.g. "LS", "LE", "LW") to servo degree lists.
    """
    if side == "left":
        group_keys = config.LEFT_ARM_GROUPS
    elif side == "right":
        group_keys = config.RIGHT_ARM_GROUPS
    else:
        raise ValueError(f"side must be 'left' or 'right', got '{side}'")

    servo_groups: dict[str, list[float]] = {}

    for group_key in group_keys:
        mappings = config.SERVO_GROUP_TO_JOINTS[group_key]
        servo_values: list[float] = []
        for joint_name, _servo_index in mappings:
            joint_index = config.JOINT_NAMES.index(joint_name)
            servo_deg = radians_to_servo_degrees(joint_angles[joint_index], joint_name, side)
            servo_values.append(servo_deg)
        servo_groups[group_key] = servo_values

    return servo_groups
