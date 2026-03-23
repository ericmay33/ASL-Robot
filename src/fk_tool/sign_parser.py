"""
Sign data normalization and parsing.

Reads raw sign dicts (from JSON or MongoDB) and produces clean ParsedSign objects
with fully-resolved keyframes ready for the FK engine.
"""

from .models import ParsedKeyframe, ParsedSign
from . import config


def parse_sign(raw_sign: dict) -> ParsedSign:
    """Parse a raw sign dictionary into a fully-resolved ParsedSign.

    Validates required fields, resolves hold-forward behavior for missing servo
    groups, fills defaults for the first keyframe, and sorts by time.

    Args:
        raw_sign: Raw sign dict with keys: token, type, duration, keyframes.

    Returns:
        A ParsedSign with all keyframes fully resolved.

    Raises:
        ValueError: If required fields are missing.
    """
    _validate_required_fields(raw_sign)

    raw_keyframes = _normalize_keyframe_list(raw_sign["keyframes"])
    sorted_keyframes = sorted(raw_keyframes, key=lambda kf: kf.get("time", 0.0))

    arm = _detect_arm_usage(sorted_keyframes)
    parsed_keyframes = _resolve_keyframes(sorted_keyframes)
    finger_data = _extract_finger_data(sorted_keyframes)

    return ParsedSign(
        token=raw_sign["token"],
        sign_type=raw_sign.get("type", "STATIC"),
        duration=raw_sign.get("duration", 1.0),
        arm=arm,
        keyframes=parsed_keyframes,
        finger_data=finger_data,
        raw=raw_sign,
    )


def parse_signs(raw_signs: list[dict]) -> list[ParsedSign]:
    """Parse a list of raw sign dicts into ParsedSign objects.

    Args:
        raw_signs: List of raw sign dictionaries.

    Returns:
        List of ParsedSign objects.
    """
    return [parse_sign(sign) for sign in raw_signs]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _validate_required_fields(raw_sign: dict) -> None:
    """Check that a raw sign dict has all required fields.

    Args:
        raw_sign: The raw sign dictionary to validate.

    Raises:
        ValueError: If a required field is missing.
    """
    required = ["token", "keyframes"]
    for field_name in required:
        if field_name not in raw_sign:
            raise ValueError(f"Sign is missing required field: '{field_name}'")


def _normalize_keyframe_list(keyframes_data: list | dict) -> list[dict]:
    """Ensure keyframes is always a list of dicts.

    Handles the edge case where keyframes might be a dict keyed by index.

    Args:
        keyframes_data: Either a list of keyframe dicts or a dict of them.

    Returns:
        List of keyframe dicts.
    """
    if isinstance(keyframes_data, list):
        return keyframes_data
    if isinstance(keyframes_data, dict):
        return list(keyframes_data.values())
    raise ValueError(f"Unexpected keyframes type: {type(keyframes_data)}")


def _detect_arm_usage(keyframes: list[dict]) -> str:
    """Determine which arm(s) a sign uses based on which servo groups appear.

    Args:
        keyframes: List of raw keyframe dicts.

    Returns:
        "left", "right", or "both".
    """
    has_left = False
    has_right = False

    left_keys = set(config.LEFT_ARM_GROUPS + ["L"])
    right_keys = set(config.RIGHT_ARM_GROUPS + ["R"])

    for keyframe in keyframes:
        for key in keyframe:
            if key in left_keys:
                has_left = True
            if key in right_keys:
                has_right = True

    if has_left and has_right:
        return "both"
    if has_right:
        return "right"
    return "left"


def _resolve_keyframes(sorted_keyframes: list[dict]) -> list[ParsedKeyframe]:
    """Resolve hold-forward behavior and fill defaults for all keyframes.

    If a servo group is missing from a keyframe, the previous keyframe's value
    carries forward. If missing from the first keyframe, defaults to 90 deg.

    Args:
        sorted_keyframes: Time-sorted list of raw keyframe dicts.

    Returns:
        List of fully-resolved ParsedKeyframe objects.
    """
    previous_left = _default_servo_dict("left")
    previous_right = _default_servo_dict("right")
    previous_left_fingers: list[float] | None = None
    previous_right_fingers: list[float] | None = None

    parsed: list[ParsedKeyframe] = []

    for raw_kf in sorted_keyframes:
        left_servos = _resolve_arm_groups(raw_kf, config.LEFT_ARM_GROUPS, previous_left)
        right_servos = _resolve_arm_groups(raw_kf, config.RIGHT_ARM_GROUPS, previous_right)

        left_fingers = _extract_group(raw_kf, "L", previous_left_fingers)
        right_fingers = _extract_group(raw_kf, "R", previous_right_fingers)

        parsed.append(ParsedKeyframe(
            time=raw_kf.get("time", 0.0),
            left_servos=left_servos,
            right_servos=right_servos,
            left_fingers=left_fingers,
            right_fingers=right_fingers,
        ))

        previous_left = left_servos
        previous_right = right_servos
        previous_left_fingers = left_fingers
        previous_right_fingers = right_fingers

    return parsed


def _default_servo_dict(side: str) -> dict[str, list[float]]:
    """Create a default servo dict (all 90 deg) for one arm side.

    Args:
        side: "left" or "right".

    Returns:
        Dict mapping group keys to default servo position lists.
    """
    if side == "left":
        groups = config.LEFT_ARM_GROUPS
    else:
        groups = config.RIGHT_ARM_GROUPS

    return {
        group: list(config.DEFAULT_SERVO_POSITIONS[group])
        for group in groups
    }


def _resolve_arm_groups(
    raw_keyframe: dict,
    group_keys: list[str],
    previous_values: dict[str, list[float]],
) -> dict[str, list[float]]:
    """Resolve servo groups for one arm from a keyframe, with hold-forward.

    Args:
        raw_keyframe: Raw keyframe dict from sign data.
        group_keys: List of group keys to resolve (e.g. ["LS", "LE", "LW"]).
        previous_values: Previous keyframe's resolved values for this arm.

    Returns:
        Dict mapping each group key to its resolved servo values.
    """
    resolved: dict[str, list[float]] = {}
    for group_key in group_keys:
        if group_key in raw_keyframe:
            resolved[group_key] = list(raw_keyframe[group_key])
        else:
            resolved[group_key] = list(previous_values[group_key])
    return resolved


def _extract_group(
    raw_keyframe: dict,
    group_key: str,
    previous_value: list[float] | None,
) -> list[float] | None:
    """Extract a single group (like finger data) with hold-forward.

    Args:
        raw_keyframe: Raw keyframe dict.
        group_key: Key to extract (e.g. "L" or "R").
        previous_value: Previous keyframe's value, or None.

    Returns:
        List of servo values, or None if never specified.
    """
    if group_key in raw_keyframe:
        return list(raw_keyframe[group_key])
    return previous_value


def _extract_finger_data(sorted_keyframes: list[dict]) -> dict:
    """Extract finger servo data across all keyframes for metadata.

    Args:
        sorted_keyframes: Time-sorted list of raw keyframe dicts.

    Returns:
        Dict with keys "L" and "R", each mapping to a list of per-keyframe values.
    """
    finger_data: dict[str, list[list[float] | None]] = {"L": [], "R": []}
    previous_left: list[float] | None = None
    previous_right: list[float] | None = None

    for raw_kf in sorted_keyframes:
        if "L" in raw_kf:
            previous_left = list(raw_kf["L"])
        if "R" in raw_kf:
            previous_right = list(raw_kf["R"])
        finger_data["L"].append(previous_left)
        finger_data["R"].append(previous_right)

    return finger_data
