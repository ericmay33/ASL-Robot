"""
Tests for the evaluation engine.

Verifies:
  1. A valid sign passes evaluation with zero errors.
  2. A sign with out-of-range servo (999) fails with servo_range_violation.
  3. A sign with non-monotonic keyframe times fails with timing error.
  4. Batch evaluation of all signs from signs_to_seed.json completes without exceptions.
"""

from pathlib import Path

import pytest

from src.fk_tool.evaluator import evaluate_sign, evaluate_batch
from src.fk_tool.sign_parser import parse_sign, parse_signs
from src.fk_tool.loaders import load_from_json


# ---------------------------------------------------------------------------
# Helpers — hand-crafted sign dicts
# ---------------------------------------------------------------------------

def _make_valid_sign() -> dict:
    """Create a minimal valid sign with reasonable servo values."""
    return {
        "token": "TEST_VALID",
        "type": "DYNAMIC",
        "duration": 2.0,
        "keyframes": [
            {
                "time": 0.0,
                "LS": [90, 90],
                "LE": [90],
                "LW": [90, 90],
                "RS": [90, 90],
                "RE": [90],
                "RW": [90, 90],
                "L": [90, 90, 90, 90, 90],
                "R": [90, 90, 90, 90, 90],
            },
            {
                "time": 1.0,
                "LS": [100, 80],
                "LE": [110],
                "LW": [85, 95],
                "RS": [100, 80],
                "RE": [110],
                "RW": [85, 95],
                "L": [80, 100, 80, 100, 80],
                "R": [80, 100, 80, 100, 80],
            },
            {
                "time": 2.0,
                "LS": [90, 90],
                "LE": [90],
                "LW": [90, 90],
                "RS": [90, 90],
                "RE": [90],
                "RW": [90, 90],
                "L": [90, 90, 90, 90, 90],
                "R": [90, 90, 90, 90, 90],
            },
        ],
    }


def _make_bad_servo_sign() -> dict:
    """Create a sign with a servo value of 999 (out of range)."""
    return {
        "token": "TEST_BAD_SERVO",
        "type": "STATIC",
        "duration": 1.0,
        "keyframes": [
            {
                "time": 0.0,
                "LS": [999, 90],
                "LE": [90],
                "LW": [90, 90],
            },
            {
                "time": 1.0,
                "LS": [90, 90],
                "LE": [90],
                "LW": [90, 90],
            },
        ],
    }


def _make_bad_timing_sign() -> dict:
    """Create a sign with a keyframe time exceeding the duration."""
    return {
        "token": "TEST_BAD_TIMING",
        "type": "DYNAMIC",
        "duration": 2.0,
        "keyframes": [
            {
                "time": 0.0,
                "LS": [90, 90],
                "LE": [90],
                "LW": [90, 90],
            },
            {
                "time": 1.0,
                "LS": [100, 90],
                "LE": [90],
                "LW": [90, 90],
            },
            {
                "time": 3.0,
                "LS": [95, 90],
                "LE": [90],
                "LW": [90, 90],
            },
        ],
    }


# ---------------------------------------------------------------------------
# Test 1: Valid sign passes
# ---------------------------------------------------------------------------

class TestValidSign:
    """A well-formed sign with reasonable values should pass all checks."""

    def test_valid_sign_passes(self) -> None:
        """Evaluate a hand-crafted valid sign and expect passed=True."""
        parsed = parse_sign(_make_valid_sign())
        evaluation = evaluate_sign(parsed)

        assert evaluation.passed is True
        assert len(evaluation.errors) == 0
        assert evaluation.token == "TEST_VALID"

    def test_valid_sign_has_metrics(self) -> None:
        """Valid sign evaluation should produce expected summary metrics."""
        parsed = parse_sign(_make_valid_sign())
        evaluation = evaluate_sign(parsed)

        assert "duration" in evaluation.metrics
        assert "num_keyframes" in evaluation.metrics
        assert "max_angular_velocity" in evaluation.metrics
        assert evaluation.metrics["duration"] == 2.0
        assert evaluation.metrics["num_keyframes"] == 3.0


# ---------------------------------------------------------------------------
# Test 2: Out-of-range servo fails
# ---------------------------------------------------------------------------

class TestBadServoRange:
    """A sign with servo value 999 should fail servo range check."""

    def test_servo_999_fails(self) -> None:
        """Servo value 999 should produce at least one FAIL."""
        parsed = parse_sign(_make_bad_servo_sign())
        evaluation = evaluate_sign(parsed)

        assert evaluation.passed is False
        assert len(evaluation.errors) >= 1

        servo_range_errors = [
            e for e in evaluation.errors if e.metric == "servo_range_violation"
        ]
        assert len(servo_range_errors) >= 1
        assert servo_range_errors[0].value == 999.0


# ---------------------------------------------------------------------------
# Test 3: Non-monotonic timing fails
# ---------------------------------------------------------------------------

class TestBadTiming:
    """A sign with non-monotonic keyframe times should fail timing check."""

    def test_keyframe_exceeds_duration_fails(self) -> None:
        """A keyframe time exceeding the sign duration should produce a timing FAIL."""
        parsed = parse_sign(_make_bad_timing_sign())
        evaluation = evaluate_sign(parsed)

        timing_errors = [
            e for e in evaluation.errors if e.metric == "timing"
        ]
        assert len(timing_errors) >= 1


# ---------------------------------------------------------------------------
# Test 4: Batch evaluation of seed file — no crashes
# ---------------------------------------------------------------------------

class TestBatchEvaluation:
    """Batch-evaluating all signs from the seed file should not crash."""

    @pytest.fixture()
    def seed_file_path(self) -> str:
        """Path to the existing signs_to_seed.json file."""
        path = Path(__file__).resolve().parents[2] / "signs" / "signs_to_seed.json"
        if not path.exists():
            pytest.skip(f"Seed file not found at {path}")
        return str(path)

    def test_batch_no_exceptions(self, seed_file_path: str) -> None:
        """Every sign in the seed file should evaluate without exceptions."""
        raw_signs = load_from_json(seed_file_path)
        parsed_signs = parse_signs(raw_signs)
        evaluations = evaluate_batch(parsed_signs)

        assert len(evaluations) == len(parsed_signs)
        for evaluation in evaluations:
            assert evaluation.token is not None
            assert isinstance(evaluation.passed, bool)
            assert isinstance(evaluation.errors, list)
            assert isinstance(evaluation.warnings, list)

    def test_batch_has_metrics(self, seed_file_path: str) -> None:
        """Every evaluation should have a non-empty metrics dict."""
        raw_signs = load_from_json(seed_file_path)
        parsed_signs = parse_signs(raw_signs)
        evaluations = evaluate_batch(parsed_signs)

        for evaluation in evaluations:
            assert len(evaluation.metrics) > 0
            assert "duration" in evaluation.metrics
