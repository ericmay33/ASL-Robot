"""
3D visualization of robot arm poses and sign animations.

Renders stick-figure arm links using matplotlib, with support for static poses,
animated signs, side-by-side comparison, and batch thumbnail grids.
"""

from __future__ import annotations

import math

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation

from . import config
from .models import ParsedSign, ParsedKeyframe
from .servo_mapper import servos_to_joint_angles
from .fk_engine import get_joint_positions, get_joint_positions_dual


# ---------------------------------------------------------------------------
# Interpolation helpers
# ---------------------------------------------------------------------------

def _lerp_servo_groups(
    group_a: dict[str, list[float]],
    group_b: dict[str, list[float]],
    fraction: float,
) -> dict[str, list[float]]:
    """Linearly interpolate between two servo group dicts.

    Args:
        group_a: Servo groups at the start of the interval.
        group_b: Servo groups at the end of the interval.
        fraction: Interpolation factor in [0.0, 1.0].

    Returns:
        Interpolated servo group dict.
    """
    result: dict[str, list[float]] = {}
    for key in group_a:
        values_a = group_a[key]
        values_b = group_b[key]
        result[key] = [
            a + (b - a) * fraction for a, b in zip(values_a, values_b)
        ]
    return result


def _lerp_fingers(
    fingers_a: list[float] | None,
    fingers_b: list[float] | None,
    fraction: float,
) -> list[float] | None:
    """Linearly interpolate between two finger value lists.

    Args:
        fingers_a: Finger servos at start, or None.
        fingers_b: Finger servos at end, or None.
        fraction: Interpolation factor in [0.0, 1.0].

    Returns:
        Interpolated finger values, or None if both inputs are None.
    """
    if fingers_a is None or fingers_b is None:
        return fingers_b if fraction >= 0.5 else fingers_a
    return [a + (b - a) * fraction for a, b in zip(fingers_a, fingers_b)]


def _interpolate_keyframes(
    keyframes: list[ParsedKeyframe],
    time: float,
) -> ParsedKeyframe:
    """Get an interpolated keyframe at an arbitrary time.

    Args:
        keyframes: Time-sorted list of fully-resolved keyframes.
        time: Target time in seconds.

    Returns:
        Interpolated ParsedKeyframe.
    """
    if time <= keyframes[0].time:
        return keyframes[0]
    if time >= keyframes[-1].time:
        return keyframes[-1]

    for i in range(len(keyframes) - 1):
        if keyframes[i].time <= time <= keyframes[i + 1].time:
            interval = keyframes[i + 1].time - keyframes[i].time
            fraction = (time - keyframes[i].time) / interval if interval > 0 else 0.0
            return ParsedKeyframe(
                time=time,
                left_servos=_lerp_servo_groups(
                    keyframes[i].left_servos, keyframes[i + 1].left_servos, fraction
                ),
                right_servos=_lerp_servo_groups(
                    keyframes[i].right_servos, keyframes[i + 1].right_servos, fraction
                ),
                left_fingers=_lerp_fingers(
                    keyframes[i].left_fingers, keyframes[i + 1].left_fingers, fraction
                ),
                right_fingers=_lerp_fingers(
                    keyframes[i].right_fingers, keyframes[i + 1].right_fingers, fraction
                ),
            )

    return keyframes[-1]


# ---------------------------------------------------------------------------
# Arm drawing
# ---------------------------------------------------------------------------

def _draw_arm_on_axes(
    ax: plt.Axes,
    positions: np.ndarray,
    label_prefix: str = "",
) -> None:
    """Draw a single arm as colored stick-figure links with joint markers.

    Args:
        ax: Matplotlib 3D axes to draw on.
        positions: 6x3 array of joint (x, y, z) positions.
        label_prefix: Optional prefix for legend labels.
    """
    for i in range(len(positions) - 1):
        color = config.LINK_COLORS[i] if i < len(config.LINK_COLORS) else "gray"
        ax.plot(
            [positions[i, 0], positions[i + 1, 0]],
            [positions[i, 1], positions[i + 1, 1]],
            [positions[i, 2], positions[i + 1, 2]],
            color=color,
            linewidth=config.LINK_LINE_WIDTH,
        )

    ax.scatter(
        positions[:, 0], positions[:, 1], positions[:, 2],
        color=config.JOINT_MARKER_COLOR,
        s=config.JOINT_MARKER_SIZE ** 2,
        zorder=5,
    )


def _draw_torso_reference(ax: plt.Axes) -> None:
    """Draw a simple vertical gray line at the body center as a torso reference.

    Args:
        ax: Matplotlib 3D axes.
    """
    ax.plot(
        [0, 0], [0, 0], [0, -config.AXIS_LIMIT],
        color="gray", linewidth=1.0, linestyle="--", alpha=0.4,
    )


def _setup_axes(ax: plt.Axes, title: str = "") -> None:
    """Configure 3D axes with labels, grid, equal aspect, and axis limits.

    Args:
        ax: Matplotlib 3D axes.
        title: Title string for the axes.
    """
    limit = config.AXIS_LIMIT
    ax.set_xlim(-limit, limit)
    ax.set_ylim(-limit, limit)
    ax.set_zlim(-limit, limit)
    ax.set_xlabel("X (in)")
    ax.set_ylabel("Y (in)")
    ax.set_zlabel("Z (in)")
    ax.set_title(title)
    ax.grid(True)
    ax.view_init(elev=20, azim=135)


def _format_finger_text(
    left_fingers: list[float] | None,
    right_fingers: list[float] | None,
) -> str:
    """Format finger servo values as a compact text annotation.

    Args:
        left_fingers: Left hand finger servos, or None.
        right_fingers: Right hand finger servos, or None.

    Returns:
        Formatted string for display.
    """
    parts: list[str] = []
    if left_fingers is not None:
        values = ", ".join(f"{v:.0f}" for v in left_fingers)
        parts.append(f"L fingers: [{values}]")
    if right_fingers is not None:
        values = ", ".join(f"{v:.0f}" for v in right_fingers)
        parts.append(f"R fingers: [{values}]")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Keyframe → positions helper
# ---------------------------------------------------------------------------

def _keyframe_to_positions(
    keyframe: ParsedKeyframe,
    arm: str,
) -> tuple[np.ndarray | None, np.ndarray | None]:
    """Convert a keyframe's servos to FK joint positions.

    Args:
        keyframe: A fully-resolved ParsedKeyframe.
        arm: "left", "right", or "both".

    Returns:
        Tuple of (left_positions, right_positions). Either may be None.
    """
    left_positions = None
    right_positions = None

    if arm in ("left", "both"):
        left_angles = servos_to_joint_angles(keyframe.left_servos, "left")
        left_positions = get_joint_positions(left_angles)
        left_positions[:, 0] = -left_positions[:, 0] - config.SHOULDER_X_OFFSET

    if arm in ("right", "both"):
        right_angles = servos_to_joint_angles(keyframe.right_servos, "right")
        right_positions = get_joint_positions(right_angles)
        right_positions[:, 0] += config.SHOULDER_X_OFFSET

    return left_positions, right_positions


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def plot_single_pose(
    joint_angles_left: np.ndarray | None = None,
    joint_angles_right: np.ndarray | None = None,
    title: str = "",
    save_path: str | None = None,
) -> None:
    """Render a static 3D plot of one arm configuration.

    Args:
        joint_angles_left: 5-element array of left arm radians, or None to skip.
        joint_angles_right: 5-element array of right arm radians, or None to skip.
        title: Plot title.
        save_path: File path to save the figure, or None to show interactively.
    """
    fig = plt.figure(figsize=(8, 8))
    ax = fig.add_subplot(111, projection="3d")
    _setup_axes(ax, title)
    _draw_torso_reference(ax)

    if joint_angles_left is not None:
        positions = get_joint_positions(joint_angles_left)
        positions[:, 0] = -positions[:, 0] - config.SHOULDER_X_OFFSET
        _draw_arm_on_axes(ax, positions, "L")

    if joint_angles_right is not None:
        positions = get_joint_positions(joint_angles_right)
        positions[:, 0] += config.SHOULDER_X_OFFSET
        _draw_arm_on_axes(ax, positions, "R")

    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
        plt.close(fig)
    else:
        plt.show()


def animate_sign(
    parsed_sign: ParsedSign,
    fps: int = 30,
    save_path: str | None = None,
) -> None:
    """Animate a parsed sign as a 3D stick-figure moving through keyframes.

    Linearly interpolates between keyframes at the given fps. Saves as GIF or
    MP4 if save_path is provided, otherwise shows an interactive window.

    Args:
        parsed_sign: A fully-parsed sign with resolved keyframes.
        fps: Frames per second for the animation.
        save_path: Output path (.gif or .mp4), or None for interactive display.
    """
    duration = parsed_sign.duration
    num_frames = max(int(duration * fps), 1)
    frame_times = [i * duration / num_frames for i in range(num_frames + 1)]

    fig = plt.figure(figsize=(8, 8))
    ax = fig.add_subplot(111, projection="3d")

    finger_text = ax.text2D(
        0.02, 0.98, "", transform=ax.transAxes,
        fontsize=7, verticalalignment="top", family="monospace",
    )

    def update(frame_index: int) -> None:
        ax.cla()
        _setup_axes(ax, f"{parsed_sign.token}  t={frame_times[frame_index]:.2f}s")
        _draw_torso_reference(ax)

        keyframe = _interpolate_keyframes(parsed_sign.keyframes, frame_times[frame_index])
        left_pos, right_pos = _keyframe_to_positions(keyframe, parsed_sign.arm)

        if left_pos is not None:
            _draw_arm_on_axes(ax, left_pos, "L")
        if right_pos is not None:
            _draw_arm_on_axes(ax, right_pos, "R")

        finger_label = _format_finger_text(keyframe.left_fingers, keyframe.right_fingers)
        ax.text2D(
            0.02, 0.98, finger_label, transform=ax.transAxes,
            fontsize=7, verticalalignment="top", family="monospace",
        )

    animation = FuncAnimation(
        fig, update, frames=len(frame_times), interval=1000 / fps, repeat=True,
    )

    _save_or_show(animation, fig, save_path, fps)


def compare_signs(
    sign_a: ParsedSign,
    sign_b: ParsedSign,
    labels: tuple[str, str] = ("A", "B"),
    save_path: str | None = None,
    fps: int = 30,
) -> None:
    """Side-by-side animated comparison of two signs.

    Args:
        sign_a: First parsed sign.
        sign_b: Second parsed sign.
        labels: Display labels for each sign.
        save_path: Output path (.gif or .mp4), or None for interactive display.
        fps: Frames per second.
    """
    max_duration = max(sign_a.duration, sign_b.duration)
    num_frames = max(int(max_duration * fps), 1)
    frame_times = [i * max_duration / num_frames for i in range(num_frames + 1)]

    fig = plt.figure(figsize=(14, 7))
    ax_a = fig.add_subplot(121, projection="3d")
    ax_b = fig.add_subplot(122, projection="3d")

    def update(frame_index: int) -> None:
        current_time = frame_times[frame_index]
        for ax, sign, label in [(ax_a, sign_a, labels[0]), (ax_b, sign_b, labels[1])]:
            ax.cla()
            _setup_axes(ax, f"{label}: {sign.token}  t={current_time:.2f}s")
            _draw_torso_reference(ax)

            clamped_time = min(current_time, sign.duration)
            keyframe = _interpolate_keyframes(sign.keyframes, clamped_time)
            left_pos, right_pos = _keyframe_to_positions(keyframe, sign.arm)

            if left_pos is not None:
                _draw_arm_on_axes(ax, left_pos)
            if right_pos is not None:
                _draw_arm_on_axes(ax, right_pos)

    animation = FuncAnimation(
        fig, update, frames=len(frame_times), interval=1000 / fps, repeat=True,
    )

    _save_or_show(animation, fig, save_path, fps)


def batch_thumbnails(
    parsed_signs: list[ParsedSign],
    columns: int = 5,
    save_path: str | None = None,
) -> None:
    """Grid of static first-keyframe poses for quick visual scanning.

    Args:
        parsed_signs: List of parsed signs to display.
        columns: Number of columns in the grid.
        save_path: Output path (.png), or None for interactive display.
    """
    count = len(parsed_signs)
    rows = math.ceil(count / columns)
    fig = plt.figure(figsize=(4 * columns, 4 * rows))

    for index, sign in enumerate(parsed_signs):
        ax = fig.add_subplot(rows, columns, index + 1, projection="3d")
        _setup_axes(ax, sign.token)
        _draw_torso_reference(ax)

        if sign.keyframes:
            first_keyframe = sign.keyframes[0]
            left_pos, right_pos = _keyframe_to_positions(first_keyframe, sign.arm)
            if left_pos is not None:
                _draw_arm_on_axes(ax, left_pos)
            if right_pos is not None:
                _draw_arm_on_axes(ax, right_pos)

    fig.tight_layout()

    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
        plt.close(fig)
    else:
        plt.show()


# ---------------------------------------------------------------------------
# Internal save/show helper
# ---------------------------------------------------------------------------

def _save_or_show(
    animation: FuncAnimation,
    fig: plt.Figure,
    save_path: str | None,
    fps: int,
) -> None:
    """Save an animation to file or display interactively.

    Args:
        animation: The matplotlib FuncAnimation object.
        fig: The figure containing the animation.
        save_path: Output path (.gif or .mp4), or None for interactive.
        fps: Frames per second for saving.
    """
    if save_path is None:
        plt.show()
        return

    if save_path.endswith(".gif"):
        animation.save(save_path, writer="pillow", fps=fps)
    elif save_path.endswith(".mp4"):
        animation.save(save_path, writer="ffmpeg", fps=fps)
    else:
        animation.save(save_path, fps=fps)

    plt.close(fig)
