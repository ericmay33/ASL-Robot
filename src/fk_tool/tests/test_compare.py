"""
Tests for the sign comparison engine (Phase 6).

Verifies:
  1. Two similar signs produce MAE > 0 with arm_agreement and both_passed True.
  2. An AI sign with out-of-range servo fails while reference passes.
  3. AI signs with no matching reference are skipped without crashing.
"""

import pytest

from src.fk_tool.evaluator import compare_signs, compare_batch
from src.fk_tool.sign_parser import parse_sign, parse_signs


# ---------------------------------------------------------------------------
# Helpers — hand-crafted sign dicts
# ---------------------------------------------------------------------------

def _make_reference_sign() -> dict:
    """Create a valid reference sign with neutral servo values."""
    return {
        "token": "TEST_COMPARE",
        "type": "DYNAMIC",
        "duration": 2.0,
        "keyframes": [
            {
                "time": 0.0,
                "LS": [90, 90], "LE": [90], "LW": [90, 90],
                "RS": [90, 90], "RE": [90], "RW": [90, 90],
                "L": [90, 90, 90, 90, 90], "R": [90, 90, 90, 90, 90],
            },
            {
                "time": 2.0,
                "LS": [100, 80], "LE": [110], "LW": [85, 95],
                "RS": [100, 80], "RE": [110], "RW": [85, 95],
                "L": [80, 100, 80, 100, 80], "R": [80, 100, 80, 100, 80],
            },
        ],
    }


def _make_ai_sign_slightly_different() -> dict:
    """Create an AI sign with same token but slightly different servo values."""
    return {
        "token": "TEST_COMPARE",
        "type": "DYNAMIC",
        "duration": 2.0,
        "keyframes": [
            {
                "time": 0.0,
                "LS": [92, 88], "LE": [93], "LW": [88, 92],
                "RS": [92, 88], "RE": [93], "RW": [88, 92],
                "L": [85, 95, 85, 95, 85], "R": [85, 95, 85, 95, 85],
            },
            {
                "time": 2.0,
                "LS": [103, 77], "LE": [113], "LW": [82, 98],
                "RS": [103, 77], "RE": [113], "RW": [82, 98],
                "L": [75, 105, 75, 105, 75], "R": [75, 105, 75, 105, 75],
            },
        ],
    }


def _make_ai_sign_bad_servo() -> dict:
    """Create an AI sign with an out-of-range servo value (999)."""
    return {
        "token": "TEST_COMPARE",
        "type": "DYNAMIC",
        "duration": 2.0,
        "keyframes": [
            {
                "time": 0.0,
                "LS": [999, 90], "LE": [90], "LW": [90, 90],
                "RS": [90, 90], "RE": [90], "RW": [90, 90],
            },
            {
                "time": 2.0,
                "LS": [90, 90], "LE": [90], "LW": [90, 90],
                "RS": [90, 90], "RE": [90], "RW": [90, 90],
            },
        ],
    }


def _make_unmatched_ai_sign() -> dict:
    """Create an AI sign with a token that has no reference match."""
    return {
        "token": "NO_MATCH_TOKEN",
        "type": "STATIC",
        "duration": 1.0,
        "keyframes": [
            {
                "time": 0.0,
                "LS": [90, 90], "LE": [90], "LW": [90, 90],
            },
            {
                "time": 1.0,
                "LS": [90, 90], "LE": [90], "LW": [90, 90],
            },
        ],
    }


# ---------------------------------------------------------------------------
# Test 1: Similar signs produce MAE > 0, both pass, arms agree
# ---------------------------------------------------------------------------

class TestSimilarSignComparison:
    """Two signs with same token but slightly different servos."""

    def test_mae_is_positive(self) -> None:
        """Slightly different servo values should produce non-zero MAE."""
        ref = parse_sign(_make_reference_sign())
        ai = parse_sign(_make_ai_sign_slightly_different())
        result = compare_signs(ai, ref)

        assert result["joint_angle_mae"] > 0
        assert result["token"] == "TEST_COMPARE"

    def test_both_pass(self) -> None:
        """Both signs should individually pass evaluation."""
        ref = parse_sign(_make_reference_sign())
        ai = parse_sign(_make_ai_sign_slightly_different())
        result = compare_signs(ai, ref)

        assert result["both_passed"] is True
        assert result["ai_evaluation"].passed is True
        assert result["ref_evaluation"].passed is True

    def test_arm_agreement(self) -> None:
        """Both signs use both arms, so arm_agreement should be True."""
        ref = parse_sign(_make_reference_sign())
        ai = parse_sign(_make_ai_sign_slightly_different())
        result = compare_signs(ai, ref)

        assert result["arm_agreement"] is True

    def test_duration_diff_is_zero(self) -> None:
        """Same duration should produce zero difference."""
        ref = parse_sign(_make_reference_sign())
        ai = parse_sign(_make_ai_sign_slightly_different())
        result = compare_signs(ai, ref)

        assert result["duration_diff"] == 0.0


# ---------------------------------------------------------------------------
# Test 2: AI sign with bad servo fails, reference passes
# ---------------------------------------------------------------------------

class TestBadAISignComparison:
    """AI sign with servo 999 should fail while reference passes."""

    def test_ai_fails_ref_passes(self) -> None:
        """AI evaluation should fail, reference should pass."""
        ref = parse_sign(_make_reference_sign())
        ai = parse_sign(_make_ai_sign_bad_servo())
        result = compare_signs(ai, ref)

        assert result["ai_evaluation"].passed is False
        assert result["ref_evaluation"].passed is True
        assert result["both_passed"] is False


# ---------------------------------------------------------------------------
# Test 3: Unmatched AI sign is skipped in batch mode
# ---------------------------------------------------------------------------

class TestUnmatchedSignBatch:
    """AI signs with no reference match should be skipped, not crash."""

    def test_unmatched_skipped_no_crash(self) -> None:
        """compare_batch should skip unmatched signs gracefully."""
        ref_signs = parse_signs([_make_reference_sign()])
        ai_signs = parse_signs([
            _make_ai_sign_slightly_different(),
            _make_unmatched_ai_sign(),
        ])

        comparisons = compare_batch(ai_signs, ref_signs)

        # Only the matched sign should be in results
        assert len(comparisons) == 1
        assert comparisons[0]["token"] == "TEST_COMPARE"

    def test_all_unmatched_returns_empty(self) -> None:
        """If no AI signs match any references, return empty list."""
        ref_signs = parse_signs([_make_reference_sign()])
        ai_signs = parse_signs([_make_unmatched_ai_sign()])

        comparisons = compare_batch(ai_signs, ref_signs)

        assert len(comparisons) == 0
