"""
Data models for the FK tool.

Dataclasses representing parsed signs, keyframes, evaluation results, and related structures.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ParsedKeyframe:
    """A single keyframe with fully-resolved servo positions for both arms.

    Attributes:
        time: Timestamp in seconds within the sign's duration.
        left_servos: Left arm servo groups — keys are "LS", "LE", "LW".
        right_servos: Right arm servo groups — keys are "RS", "RE", "RW".
        left_fingers: 5-element finger servo list for the left hand, or None.
        right_fingers: 5-element finger servo list for the right hand, or None.
    """
    time: float
    left_servos: dict[str, list[float]] = field(default_factory=dict)
    right_servos: dict[str, list[float]] = field(default_factory=dict)
    left_fingers: list[float] | None = None
    right_fingers: list[float] | None = None


@dataclass
class ParsedSign:
    """A fully-parsed sign ready for FK processing.

    Attributes:
        token: The sign's name/identifier (e.g. "HELLO").
        sign_type: "STATIC" or "DYNAMIC".
        duration: Total sign duration in seconds.
        arm: Which arm(s) the sign uses — "left", "right", or "both".
        keyframes: Time-sorted list of fully-resolved keyframes.
        finger_data: Per-keyframe finger states (for display only).
        raw: Original unmodified sign dictionary for reference.
    """
    token: str
    sign_type: str
    duration: float
    arm: str
    keyframes: list[ParsedKeyframe]
    finger_data: dict = field(default_factory=dict)
    raw: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Evaluation models
# ---------------------------------------------------------------------------

@dataclass
class EvalIssue:
    """A single evaluation issue found during sign analysis.

    Attributes:
        level: Severity — "FAIL", "WARN", or "INFO".
        metric: Machine-readable metric name (e.g. "servo_range_violation").
        message: Human-readable description of the issue.
        keyframe_index: Which keyframe triggered this, or None if sign-level.
        joint_name: Which joint is affected, or None if not joint-specific.
        value: The offending value, or None.
        limit: The limit that was exceeded, or None.
    """
    level: str
    metric: str
    message: str
    keyframe_index: int | None = None
    joint_name: str | None = None
    value: float | None = None
    limit: float | None = None


@dataclass
class SignEvaluation:
    """Complete evaluation result for one sign.

    Attributes:
        token: The sign's name/identifier.
        passed: True if no FAIL-level issues were found.
        errors: List of FAIL-level issues.
        warnings: List of WARN-level issues.
        info: List of INFO-level issues.
        metrics: Summary metrics dict (string keys, float values).
    """
    token: str
    passed: bool
    errors: list[EvalIssue] = field(default_factory=list)
    warnings: list[EvalIssue] = field(default_factory=list)
    info: list[EvalIssue] = field(default_factory=list)
    metrics: dict[str, float] = field(default_factory=dict)
