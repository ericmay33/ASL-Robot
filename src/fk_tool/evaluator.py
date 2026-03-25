"""
Sign evaluation engine.

Runs a battery of physical plausibility checks on parsed signs and produces
structured SignEvaluation results with errors, warnings, and summary metrics.
"""

from __future__ import annotations

import math

import numpy as np

from . import config
from .models import ParsedSign, ParsedKeyframe, EvalIssue, SignEvaluation
from .servo_mapper import servo_degrees_to_radians, servos_to_joint_angles


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def evaluate_sign(parsed_sign: ParsedSign) -> SignEvaluation:
    """Run all evaluation checks on a parsed sign.

    Args:
        parsed_sign: A fully-parsed sign with resolved keyframes.

    Returns:
        A SignEvaluation with all issues and summary metrics.
    """
    issues: list[EvalIssue] = []

    issues.extend(check_servo_range(parsed_sign))
    issues.extend(check_joint_limits(parsed_sign))
    issues.extend(check_timing(parsed_sign))
    issues.extend(check_angular_velocity(parsed_sign))
    issues.extend(check_duration(parsed_sign))
    issues.extend(check_keyframe_completeness(parsed_sign))

    errors = [issue for issue in issues if issue.level == "FAIL"]
    warnings = [issue for issue in issues if issue.level == "WARN"]
    info = [issue for issue in issues if issue.level == "INFO"]

    metrics = _compute_summary_metrics(parsed_sign, issues)

    return SignEvaluation(
        token=parsed_sign.token,
        passed=len(errors) == 0,
        errors=errors,
        warnings=warnings,
        info=info,
        metrics=metrics,
    )


def evaluate_batch(signs: list[ParsedSign]) -> list[SignEvaluation]:
    """Evaluate a list of parsed signs, printing progress.

    Args:
        signs: List of ParsedSign objects.

    Returns:
        List of SignEvaluation results.
    """
    evaluations: list[SignEvaluation] = []
    total = len(signs)

    for index, sign in enumerate(signs):
        evaluation = evaluate_sign(sign)
        status = "PASS" if evaluation.passed else "FAIL"
        print(f"  [{index + 1}/{total}] {sign.token}: {status}")
        evaluations.append(evaluation)

    return evaluations


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

def check_servo_range(parsed_sign: ParsedSign) -> list[EvalIssue]:
    """Check that all servo values are within [0, 180] degrees.

    Args:
        parsed_sign: The sign to check.

    Returns:
        List of FAIL-level issues for out-of-range servos.
    """
    issues: list[EvalIssue] = []

    for kf_index, keyframe in enumerate(parsed_sign.keyframes):
        all_groups = {**keyframe.left_servos, **keyframe.right_servos}
        _check_servo_groups_range(all_groups, kf_index, issues)
        _check_finger_range(keyframe.left_fingers, "L", kf_index, issues)
        _check_finger_range(keyframe.right_fingers, "R", kf_index, issues)

    return issues


def _check_servo_groups_range(
    groups: dict[str, list[float]],
    keyframe_index: int,
    issues: list[EvalIssue],
) -> None:
    """Check servo group values against valid range.

    Args:
        groups: Servo groups dict.
        keyframe_index: Index of the keyframe being checked.
        issues: List to append issues to.
    """
    for group_key, values in groups.items():
        for servo_index, servo_value in enumerate(values):
            if servo_value < config.SERVO_MIN_DEGREES or servo_value > config.SERVO_MAX_DEGREES:
                issues.append(EvalIssue(
                    level="FAIL",
                    metric="servo_range_violation",
                    message=(
                        f"Servo {group_key}[{servo_index}] = {servo_value:.1f} "
                        f"is outside [{config.SERVO_MIN_DEGREES}, {config.SERVO_MAX_DEGREES}]"
                    ),
                    keyframe_index=keyframe_index,
                    joint_name=f"{group_key}[{servo_index}]",
                    value=servo_value,
                    limit=config.SERVO_MAX_DEGREES,
                ))


def _check_finger_range(
    fingers: list[float] | None,
    side_label: str,
    keyframe_index: int,
    issues: list[EvalIssue],
) -> None:
    """Check finger servo values against valid range.

    Args:
        fingers: Finger servo values or None.
        side_label: "L" or "R".
        keyframe_index: Index of the keyframe being checked.
        issues: List to append issues to.
    """
    if fingers is None:
        return
    for finger_index, value in enumerate(fingers):
        if value < config.SERVO_MIN_DEGREES or value > config.SERVO_MAX_DEGREES:
            issues.append(EvalIssue(
                level="FAIL",
                metric="servo_range_violation",
                message=(
                    f"Finger {side_label}[{finger_index}] = {value:.1f} "
                    f"is outside [{config.SERVO_MIN_DEGREES}, {config.SERVO_MAX_DEGREES}]"
                ),
                keyframe_index=keyframe_index,
                joint_name=f"{side_label}[{finger_index}]",
                value=value,
                limit=config.SERVO_MAX_DEGREES,
            ))


def check_joint_limits(parsed_sign: ParsedSign) -> list[EvalIssue]:
    """Check that joint angles (converted from servos) are within calibrated limits.

    Args:
        parsed_sign: The sign to check.

    Returns:
        List of FAIL-level issues for joints exceeding mechanical limits.
    """
    issues: list[EvalIssue] = []

    for kf_index, keyframe in enumerate(parsed_sign.keyframes):
        _check_arm_joint_limits(keyframe.left_servos, "left", kf_index, issues)
        _check_arm_joint_limits(keyframe.right_servos, "right", kf_index, issues)

    return issues


def _check_arm_joint_limits(
    servo_groups: dict[str, list[float]],
    side: str,
    keyframe_index: int,
    issues: list[EvalIssue],
) -> None:
    """Check joint limits for one arm's servo groups.

    Args:
        servo_groups: Servo groups for one arm.
        side: "left" or "right".
        keyframe_index: Index of the keyframe being checked.
        issues: List to append issues to.
    """
    group_keys = config.LEFT_ARM_GROUPS if side == "left" else config.RIGHT_ARM_GROUPS

    for group_key in group_keys:
        if group_key not in servo_groups:
            continue
        for joint_name, servo_index in config.SERVO_GROUP_TO_JOINTS[group_key]:
            servo_value = servo_groups[group_key][servo_index]
            joint_rad = servo_degrees_to_radians(servo_value, joint_name, side)
            calibration = config.joint_calibration_for_side(side)[joint_name]

            if joint_rad < calibration.min_rad:
                issues.append(EvalIssue(
                    level="FAIL",
                    metric="joint_limit_violation",
                    message=(
                        f"{side} {joint_name} = {math.degrees(joint_rad):.1f} deg "
                        f"< min {math.degrees(calibration.min_rad):.1f} deg"
                    ),
                    keyframe_index=keyframe_index,
                    joint_name=joint_name,
                    value=joint_rad,
                    limit=calibration.min_rad,
                ))
            elif joint_rad > calibration.max_rad:
                issues.append(EvalIssue(
                    level="FAIL",
                    metric="joint_limit_violation",
                    message=(
                        f"{side} {joint_name} = {math.degrees(joint_rad):.1f} deg "
                        f"> max {math.degrees(calibration.max_rad):.1f} deg"
                    ),
                    keyframe_index=keyframe_index,
                    joint_name=joint_name,
                    value=joint_rad,
                    limit=calibration.max_rad,
                ))


def check_timing(parsed_sign: ParsedSign) -> list[EvalIssue]:
    """Check that keyframe times are monotonically increasing and well-formed.

    Verifies: first keyframe time is 0.0, last keyframe time <= duration,
    last keyframe time > 0 (for multi-keyframe signs), and times are
    strictly non-decreasing. The last keyframe is allowed to be earlier
    than the duration — the robot holds the final pose for remaining time.

    Args:
        parsed_sign: The sign to check.

    Returns:
        List of FAIL-level issues for timing violations.
    """
    issues: list[EvalIssue] = []
    keyframes = parsed_sign.keyframes

    if not keyframes:
        issues.append(EvalIssue(
            level="FAIL", metric="timing", message="Sign has no keyframes",
        ))
        return issues

    if keyframes[0].time != 0.0:
        issues.append(EvalIssue(
            level="FAIL",
            metric="timing",
            message=f"First keyframe time is {keyframes[0].time}, expected 0.0",
            keyframe_index=0,
            value=keyframes[0].time,
            limit=0.0,
        ))

    if len(keyframes) > 1 and keyframes[-1].time > parsed_sign.duration:
        issues.append(EvalIssue(
            level="FAIL",
            metric="timing",
            message=(
                f"Last keyframe time {keyframes[-1].time} "
                f"exceeds sign duration {parsed_sign.duration}"
            ),
            keyframe_index=len(keyframes) - 1,
            value=keyframes[-1].time,
            limit=parsed_sign.duration,
        ))

    if len(keyframes) > 1 and keyframes[-1].time <= 0.0:
        issues.append(EvalIssue(
            level="FAIL",
            metric="timing",
            message=(
                f"Last keyframe time is {keyframes[-1].time}, "
                f"expected > 0.0 for a multi-keyframe sign"
            ),
            keyframe_index=len(keyframes) - 1,
            value=keyframes[-1].time,
            limit=0.0,
        ))

    for i in range(1, len(keyframes)):
        if keyframes[i].time < keyframes[i - 1].time:
            issues.append(EvalIssue(
                level="FAIL",
                metric="timing",
                message=(
                    f"Keyframe {i} time {keyframes[i].time} "
                    f"< keyframe {i-1} time {keyframes[i-1].time}"
                ),
                keyframe_index=i,
                value=keyframes[i].time,
                limit=keyframes[i - 1].time,
            ))

    return issues


def check_angular_velocity(parsed_sign: ParsedSign) -> list[EvalIssue]:
    """Check that servo angular velocity between keyframes is physically possible.

    Args:
        parsed_sign: The sign to check.

    Returns:
        List of WARN-level issues for excessive angular velocity.
    """
    issues: list[EvalIssue] = []
    keyframes = parsed_sign.keyframes

    for i in range(1, len(keyframes)):
        time_delta = keyframes[i].time - keyframes[i - 1].time
        if time_delta <= 0:
            continue
        _check_velocity_between_keyframes(
            keyframes[i - 1], keyframes[i], time_delta, i, issues,
        )

    return issues


def _check_velocity_between_keyframes(
    keyframe_before: ParsedKeyframe,
    keyframe_after: ParsedKeyframe,
    time_delta: float,
    keyframe_index: int,
    issues: list[EvalIssue],
) -> None:
    """Check angular velocity between two adjacent keyframes.

    Args:
        keyframe_before: The earlier keyframe.
        keyframe_after: The later keyframe.
        time_delta: Time between the two keyframes in seconds.
        keyframe_index: Index of the later keyframe.
        issues: List to append issues to.
    """
    all_pairs = [
        (keyframe_before.left_servos, keyframe_after.left_servos),
        (keyframe_before.right_servos, keyframe_after.right_servos),
    ]

    for groups_before, groups_after in all_pairs:
        for group_key in groups_before:
            values_before = groups_before[group_key]
            values_after = groups_after[group_key]
            for servo_index, (val_a, val_b) in enumerate(zip(values_before, values_after)):
                velocity = abs(val_b - val_a) / time_delta
                if velocity > config.MAX_ANGULAR_VELOCITY_DEG_PER_SEC:
                    issues.append(EvalIssue(
                        level="WARN",
                        metric="angular_velocity",
                        message=(
                            f"{group_key}[{servo_index}] velocity {velocity:.0f} deg/s "
                            f"exceeds {config.MAX_ANGULAR_VELOCITY_DEG_PER_SEC:.0f} deg/s"
                        ),
                        keyframe_index=keyframe_index,
                        joint_name=f"{group_key}[{servo_index}]",
                        value=velocity,
                        limit=config.MAX_ANGULAR_VELOCITY_DEG_PER_SEC,
                    ))


def check_duration(parsed_sign: ParsedSign) -> list[EvalIssue]:
    """Check that sign duration is within a reasonable range.

    Args:
        parsed_sign: The sign to check.

    Returns:
        List of WARN-level issues for unusual durations.
    """
    issues: list[EvalIssue] = []
    duration = parsed_sign.duration

    if duration < config.MIN_SIGN_DURATION_SEC:
        issues.append(EvalIssue(
            level="WARN",
            metric="duration",
            message=(
                f"Duration {duration}s is below minimum "
                f"{config.MIN_SIGN_DURATION_SEC}s"
            ),
            value=duration,
            limit=config.MIN_SIGN_DURATION_SEC,
        ))
    elif duration > config.MAX_SIGN_DURATION_SEC:
        issues.append(EvalIssue(
            level="WARN",
            metric="duration",
            message=(
                f"Duration {duration}s exceeds maximum "
                f"{config.MAX_SIGN_DURATION_SEC}s"
            ),
            value=duration,
            limit=config.MAX_SIGN_DURATION_SEC,
        ))

    return issues


def check_keyframe_completeness(parsed_sign: ParsedSign) -> list[EvalIssue]:
    """Check that the first keyframe has at least one servo group defined.

    Args:
        parsed_sign: The sign to check.

    Returns:
        List of WARN-level issues if the first keyframe is empty.
    """
    issues: list[EvalIssue] = []

    if not parsed_sign.keyframes:
        return issues

    first = parsed_sign.keyframes[0]
    has_any_data = bool(first.left_servos or first.right_servos)

    if not has_any_data:
        issues.append(EvalIssue(
            level="WARN",
            metric="keyframe_completeness",
            message="First keyframe has no servo group data",
            keyframe_index=0,
        ))

    return issues


# ---------------------------------------------------------------------------
# Summary metrics
# ---------------------------------------------------------------------------

def _compute_summary_metrics(
    parsed_sign: ParsedSign,
    issues: list[EvalIssue],
) -> dict[str, float]:
    """Compute summary metrics for the evaluation result.

    Args:
        parsed_sign: The evaluated sign.
        issues: All issues found during evaluation.

    Returns:
        Dict of metric name to float value.
    """
    max_velocity = _find_max_angular_velocity(parsed_sign)

    arms_used_value = {"left": 1.0, "right": 2.0, "both": 3.0}.get(
        parsed_sign.arm, 0.0
    )

    return {
        "duration": parsed_sign.duration,
        "num_keyframes": float(len(parsed_sign.keyframes)),
        "max_angular_velocity": max_velocity,
        "num_errors": float(sum(1 for i in issues if i.level == "FAIL")),
        "num_warnings": float(sum(1 for i in issues if i.level == "WARN")),
        "arms_used": arms_used_value,
    }


def _find_max_angular_velocity(parsed_sign: ParsedSign) -> float:
    """Find the maximum angular velocity across all keyframe transitions.

    Args:
        parsed_sign: The sign to analyze.

    Returns:
        Maximum angular velocity in degrees per second, or 0.0.
    """
    max_velocity = 0.0
    keyframes = parsed_sign.keyframes

    for i in range(1, len(keyframes)):
        time_delta = keyframes[i].time - keyframes[i - 1].time
        if time_delta <= 0:
            continue

        for groups_before, groups_after in [
            (keyframes[i - 1].left_servos, keyframes[i].left_servos),
            (keyframes[i - 1].right_servos, keyframes[i].right_servos),
        ]:
            for group_key in groups_before:
                for val_a, val_b in zip(groups_before[group_key], groups_after[group_key]):
                    velocity = abs(val_b - val_a) / time_delta
                    max_velocity = max(max_velocity, velocity)

    return max_velocity


# ---------------------------------------------------------------------------
# Sign comparison (Phase 6)
# ---------------------------------------------------------------------------

def compare_signs(
    ai_sign: ParsedSign,
    ref_sign: ParsedSign,
) -> dict:
    """Compare an AI-generated sign against a reference sign.

    Both signs must share the same token. Each is evaluated independently,
    then comparison metrics are computed between them.

    Args:
        ai_sign: The AI-generated parsed sign.
        ref_sign: The reference (database) parsed sign.

    Returns:
        Dict with keys: token, ai_evaluation, ref_evaluation, joint_angle_mae,
        duration_diff, keyframe_count_diff, arm_agreement, both_passed.
    """
    assert ai_sign.token == ref_sign.token, (
        f"Token mismatch: AI='{ai_sign.token}' vs ref='{ref_sign.token}'"
    )

    ai_evaluation = evaluate_sign(ai_sign)
    ref_evaluation = evaluate_sign(ref_sign)

    joint_angle_mae = _compute_joint_angle_mae(ai_sign, ref_sign)
    duration_diff = abs(ai_sign.duration - ref_sign.duration)
    keyframe_count_diff = abs(len(ai_sign.keyframes) - len(ref_sign.keyframes))
    arm_agreement = ai_sign.arm == ref_sign.arm

    return {
        "token": ai_sign.token,
        "ai_evaluation": ai_evaluation,
        "ref_evaluation": ref_evaluation,
        "joint_angle_mae": joint_angle_mae,
        "duration_diff": duration_diff,
        "keyframe_count_diff": keyframe_count_diff,
        "arm_agreement": arm_agreement,
        "both_passed": ai_evaluation.passed and ref_evaluation.passed,
    }


def compare_batch(
    ai_signs: list[ParsedSign],
    ref_signs: list[ParsedSign],
) -> list[dict]:
    """Compare a batch of AI signs against reference signs, matched by token.

    AI signs with no matching reference are skipped with a warning printed.

    Args:
        ai_signs: List of AI-generated parsed signs.
        ref_signs: List of reference parsed signs.

    Returns:
        List of comparison dicts (one per matched token).
    """
    ref_by_token = {sign.token: sign for sign in ref_signs}
    comparisons: list[dict] = []

    for ai_sign in ai_signs:
        if ai_sign.token not in ref_by_token:
            print(f"  WARNING: No reference found for AI sign '{ai_sign.token}', skipping")
            continue
        comparison = compare_signs(ai_sign, ref_by_token[ai_sign.token])
        print(f"  {ai_sign.token}: MAE={comparison['joint_angle_mae']:.4f} rad")
        comparisons.append(comparison)

    return comparisons


def _compute_joint_angle_mae(
    sign_a: ParsedSign,
    sign_b: ParsedSign,
) -> float:
    """Compute mean absolute error of joint angles between two signs.

    For each keyframe in sign_a, finds the nearest-time keyframe in sign_b,
    converts both to joint angles, and computes the mean absolute difference
    across all joints and all matched keyframe pairs.

    Args:
        sign_a: First parsed sign.
        sign_b: Second parsed sign.

    Returns:
        Mean absolute error in radians across all joints and keyframes.
    """
    if not sign_a.keyframes or not sign_b.keyframes:
        return 0.0

    total_error = 0.0
    total_comparisons = 0

    for keyframe_a in sign_a.keyframes:
        keyframe_b = _find_nearest_keyframe(keyframe_a.time, sign_b.keyframes)
        error, count = _keyframe_joint_angle_error(keyframe_a, keyframe_b)
        total_error += error
        total_comparisons += count

    if total_comparisons == 0:
        return 0.0
    return total_error / total_comparisons


def _find_nearest_keyframe(
    target_time: float,
    keyframes: list[ParsedKeyframe],
) -> ParsedKeyframe:
    """Find the keyframe with the time closest to target_time.

    Args:
        target_time: The time to match against.
        keyframes: List of keyframes to search.

    Returns:
        The keyframe with the nearest time.
    """
    return min(keyframes, key=lambda kf: abs(kf.time - target_time))


def _keyframe_joint_angle_error(
    keyframe_a: ParsedKeyframe,
    keyframe_b: ParsedKeyframe,
) -> tuple[float, int]:
    """Compute sum of absolute joint angle errors between two keyframes.

    Compares both left and right arm joint angles.

    Args:
        keyframe_a: First keyframe.
        keyframe_b: Second keyframe.

    Returns:
        Tuple of (total_absolute_error, number_of_comparisons).
    """
    total_error = 0.0
    count = 0

    for side, servos_attr in [("left", "left_servos"), ("right", "right_servos")]:
        angles_a = servos_to_joint_angles(getattr(keyframe_a, servos_attr), side)
        angles_b = servos_to_joint_angles(getattr(keyframe_b, servos_attr), side)
        total_error += float(np.sum(np.abs(angles_a - angles_b)))
        count += config.NUM_JOINTS

    return total_error, count
