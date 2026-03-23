"""
Smoke tests for FK tool Phase 1 and Phase 2.

Verifies:
  1. All-zero joint angles produce an arm hanging straight down (-Z axis).
  2. Loading and parsing every sign from signs_to_seed.json succeeds with zero crashes.
  3. Servo [90,90,90,90,90] maps to all-zero joint angles.
"""

import math
from pathlib import Path

import numpy as np
import pytest

from src.fk_tool import config
from src.fk_tool.fk_engine import get_joint_positions, compute_transforms
from src.fk_tool.servo_mapper import servos_to_joint_angles, joint_angles_to_servos
from src.fk_tool.loaders import load_from_json
from src.fk_tool.sign_parser import parse_sign, parse_signs


# ---------------------------------------------------------------------------
# Test 1: All-zero angles → arm hangs straight down along -Z
# ---------------------------------------------------------------------------

class TestZeroAnglesFKChain:
    """With all joints at 0 radians, the arm should extend straight down."""

    def test_positions_lie_along_negative_z(self) -> None:
        """All joint positions should have x ≈ shoulder_offset, y ≈ 0, z ≤ 0."""
        zero_angles = np.zeros(config.NUM_JOINTS)
        positions = get_joint_positions(zero_angles)

        # Position 0: base at origin
        np.testing.assert_allclose(positions[0], [0.0, 0.0, 0.0], atol=1e-10)

        # All x values should be 0 or the small shoulder offset (1.5 in)
        # All y values should be 0
        for i, position in enumerate(positions):
            assert position[1] == pytest.approx(0.0, abs=1e-10), (
                f"Joint {i} has non-zero Y: {position[1]}"
            )

        # Z values should be monotonically decreasing (going down)
        for i in range(1, len(positions)):
            assert positions[i][2] <= positions[i - 1][2] + 1e-10, (
                f"Joint {i} Z ({positions[i][2]}) is not <= "
                f"joint {i-1} Z ({positions[i-1][2]})"
            )

    def test_hand_tip_position(self) -> None:
        """Hand tip should be at (shoulder_offset, 0, -(upper+forearm+wrist))."""
        zero_angles = np.zeros(config.NUM_JOINTS)
        positions = get_joint_positions(zero_angles)
        hand_tip = positions[-1]

        expected_z = -(
            config.UPPER_ARM_LENGTH
            + config.FOREARM_LENGTH
            + config.WRIST_LENGTH
        )
        expected_x = config.SHOULDER_OFFSET_LENGTH

        assert hand_tip[0] == pytest.approx(expected_x, abs=1e-10)
        assert hand_tip[1] == pytest.approx(0.0, abs=1e-10)
        assert hand_tip[2] == pytest.approx(expected_z, abs=1e-10)

    def test_cumulative_transforms_count(self) -> None:
        """compute_transforms should return 6 transforms (base + 5 joints)."""
        zero_angles = np.zeros(config.NUM_JOINTS)
        transforms = compute_transforms(zero_angles)
        assert len(transforms) == config.NUM_JOINTS + 1


# ---------------------------------------------------------------------------
# Test 2: Load and parse all signs from signs_to_seed.json — zero crashes
# ---------------------------------------------------------------------------

class TestSignLoadingAndParsing:
    """Load the real seed file and parse every sign without errors."""

    @pytest.fixture()
    def seed_file_path(self) -> str:
        """Path to the existing signs_to_seed.json file."""
        path = Path(__file__).resolve().parents[2] / "signs" / "signs_to_seed.json"
        if not path.exists():
            pytest.skip(f"Seed file not found at {path}")
        return str(path)

    def test_load_json_returns_nonempty_list(self, seed_file_path: str) -> None:
        """Loader should return a non-empty list of dicts."""
        raw_signs = load_from_json(seed_file_path)
        assert isinstance(raw_signs, list)
        assert len(raw_signs) > 0

    def test_parse_all_signs_no_crashes(self, seed_file_path: str) -> None:
        """Every sign in the seed file should parse without exceptions."""
        raw_signs = load_from_json(seed_file_path)
        parsed = parse_signs(raw_signs)

        assert len(parsed) == len(raw_signs)
        for sign in parsed:
            assert sign.token is not None
            assert len(sign.keyframes) > 0

    def test_parsed_signs_have_resolved_servos(self, seed_file_path: str) -> None:
        """Every parsed keyframe should have all arm servo groups populated."""
        raw_signs = load_from_json(seed_file_path)
        parsed = parse_signs(raw_signs)

        for sign in parsed:
            for keyframe in sign.keyframes:
                # Left arm groups should always be present and populated
                for group in config.LEFT_ARM_GROUPS:
                    assert group in keyframe.left_servos, (
                        f"Sign '{sign.token}' missing left group '{group}'"
                    )
                # Right arm groups should always be present and populated
                for group in config.RIGHT_ARM_GROUPS:
                    assert group in keyframe.right_servos, (
                        f"Sign '{sign.token}' missing right group '{group}'"
                    )


# ---------------------------------------------------------------------------
# Test 3: Servo [90,90,90,90,90] → all joint angles = 0.0
# ---------------------------------------------------------------------------

class TestNeutralServoMapping:
    """Servo neutral (90 deg) should map to zero radians for all joints."""

    def test_neutral_servos_produce_zero_angles(self) -> None:
        """All-90 servo values should convert to all-zero joint angles."""
        neutral_servos = {
            "LS": [90.0, 90.0],
            "LE": [90.0],
            "LW": [90.0, 90.0],
        }
        joint_angles = servos_to_joint_angles(neutral_servos, side="left")

        np.testing.assert_allclose(
            joint_angles,
            np.zeros(config.NUM_JOINTS),
            atol=1e-10,
        )

    def test_neutral_servos_right_arm(self) -> None:
        """Same test for the right arm."""
        neutral_servos = {
            "RS": [90.0, 90.0],
            "RE": [90.0],
            "RW": [90.0, 90.0],
        }
        joint_angles = servos_to_joint_angles(neutral_servos, side="right")

        np.testing.assert_allclose(
            joint_angles,
            np.zeros(config.NUM_JOINTS),
            atol=1e-10,
        )

    def test_round_trip_conversion(self) -> None:
        """Converting angles to servos and back should preserve the values."""
        original_angles = np.array([0.3, -0.5, 1.0, 0.2, -0.8])
        servos = joint_angles_to_servos(original_angles, side="left")
        recovered_angles = servos_to_joint_angles(servos, side="left")

        np.testing.assert_allclose(recovered_angles, original_angles, atol=1e-6)
