"""
Command-line interface for the FK tool.

Provides `evaluate`, `visualize`, and `compare` subcommands via argparse.
"""

from __future__ import annotations

import argparse
import sys

from .loaders import load_from_json, load_from_mongodb, load_from_ai_output
from .sign_parser import parse_signs
from .evaluator import evaluate_batch, compare_batch
from .report import (
    print_console_summary,
    export_report,
    print_comparison_summary,
    export_comparison_report,
)
from .servo_mapper import servos_to_joint_angles
from .visualizer import plot_single_pose, animate_sign


def main(argv: list[str] | None = None) -> None:
    """Parse arguments and dispatch to the appropriate subcommand.

    Args:
        argv: Command-line arguments, or None to use sys.argv.
    """
    parser = argparse.ArgumentParser(
        prog="fk_tool",
        description="ASL Robot Forward Kinematics Tool",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    _build_evaluate_parser(subparsers)
    _build_visualize_parser(subparsers)
    _build_compare_parser(subparsers)

    args = parser.parse_args(argv)

    if args.command == "evaluate":
        _run_evaluate(args)
    elif args.command == "visualize":
        _run_visualize(args)
    elif args.command == "compare":
        _run_compare(args)


# ---------------------------------------------------------------------------
# Subcommand parsers
# ---------------------------------------------------------------------------

def _build_evaluate_parser(subparsers: argparse._SubParsersAction) -> None:
    """Add the 'evaluate' subcommand to the parser.

    Args:
        subparsers: The subparsers action to add to.
    """
    evaluate_parser = subparsers.add_parser(
        "evaluate", help="Evaluate signs for physical plausibility",
    )

    source_group = evaluate_parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument(
        "--input", default=None, help="Path to signs JSON file",
    )
    source_group.add_argument(
        "--source", choices=["mongodb"], default=None,
        help="Load signs from MongoDB instead of a file",
    )

    evaluate_parser.add_argument(
        "--token", default=None, help="Evaluate only this specific sign token",
    )
    evaluate_parser.add_argument(
        "--tokens", nargs="+", default=None,
        help="Evaluate only these sign tokens (multiple, for MongoDB source)",
    )
    evaluate_parser.add_argument(
        "--report", default=None, help="Path to save report (.csv or .html)",
    )


def _build_visualize_parser(subparsers: argparse._SubParsersAction) -> None:
    """Add the 'visualize' subcommand to the parser.

    Args:
        subparsers: The subparsers action to add to.
    """
    visualize_parser = subparsers.add_parser(
        "visualize", help="Visualize a sign as 3D stick figure",
    )

    source_group = visualize_parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument(
        "--input", default=None, help="Path to signs JSON file",
    )
    source_group.add_argument(
        "--source", choices=["mongodb"], default=None,
        help="Load signs from MongoDB",
    )

    visualize_parser.add_argument(
        "--token", required=True, help="Sign token to visualize",
    )
    visualize_parser.add_argument(
        "--animate", action="store_true", help="Animate through keyframes",
    )
    visualize_parser.add_argument(
        "--save", default=None, help="Save to file (.png, .gif, or .mp4)",
    )


def _build_compare_parser(subparsers: argparse._SubParsersAction) -> None:
    """Add the 'compare' subcommand to the parser.

    Args:
        subparsers: The subparsers action to add to.
    """
    compare_parser = subparsers.add_parser(
        "compare", help="Compare AI-generated signs against reference signs",
    )

    compare_parser.add_argument(
        "--ai-input", required=True, help="Path to AI-generated signs JSON file",
    )

    ref_group = compare_parser.add_mutually_exclusive_group(required=True)
    ref_group.add_argument(
        "--ref-input", default=None, help="Path to reference signs JSON file",
    )
    ref_group.add_argument(
        "--ref-source", choices=["mongodb"], default=None,
        help="Load reference signs from MongoDB",
    )

    compare_parser.add_argument(
        "--report", default=None, help="Path to save comparison report (.csv or .html)",
    )


# ---------------------------------------------------------------------------
# Data loading helpers
# ---------------------------------------------------------------------------

def _load_signs_from_args(args: argparse.Namespace) -> list[dict]:
    """Load raw sign dicts based on --input or --source flag.

    Args:
        args: Parsed args with input, source, and optionally token/tokens fields.

    Returns:
        List of raw sign dicts.
    """
    if args.source == "mongodb":
        tokens_filter = _collect_token_filters(args)
        print(f"Loading signs from MongoDB...")
        return load_from_mongodb(tokens=tokens_filter)

    print(f"Loading signs from: {args.input}")
    return load_from_json(args.input)


def _collect_token_filters(args: argparse.Namespace) -> list[str] | None:
    """Gather token filters from --token and --tokens args.

    Args:
        args: Parsed args.

    Returns:
        Combined list of token names, or None if no filters specified.
    """
    tokens: list[str] = []
    if getattr(args, "token", None):
        tokens.append(args.token)
    if getattr(args, "tokens", None):
        tokens.extend(args.tokens)
    return tokens if tokens else None


# ---------------------------------------------------------------------------
# Subcommand runners
# ---------------------------------------------------------------------------

def _run_evaluate(args: argparse.Namespace) -> None:
    """Execute the evaluate subcommand.

    Args:
        args: Parsed arguments.
    """
    raw_signs = _load_signs_from_args(args)
    parsed_signs = parse_signs(raw_signs)

    if args.token and args.source != "mongodb":
        parsed_signs = [s for s in parsed_signs if s.token == args.token]
        if not parsed_signs:
            print(f"Error: Token '{args.token}' not found.")
            sys.exit(1)

    print(f"Evaluating {len(parsed_signs)} sign(s)...")
    evaluations = evaluate_batch(parsed_signs)

    print_console_summary(evaluations)

    if args.report:
        export_report(evaluations, args.report)


def _run_visualize(args: argparse.Namespace) -> None:
    """Execute the visualize subcommand.

    Args:
        args: Parsed arguments.
    """
    if args.source == "mongodb":
        print("Loading signs from MongoDB...")
        raw_signs = load_from_mongodb(tokens=[args.token])
    else:
        print(f"Loading signs from: {args.input}")
        raw_signs = load_from_json(args.input)

    parsed_signs = parse_signs(raw_signs)

    matching = [s for s in parsed_signs if s.token == args.token]
    if not matching:
        print(f"Error: Token '{args.token}' not found.")
        sys.exit(1)

    sign = matching[0]

    if args.animate:
        print(f"Animating '{sign.token}' ({sign.duration}s, {len(sign.keyframes)} keyframes)")
        animate_sign(sign, save_path=args.save)
    else:
        print(f"Plotting first keyframe of '{sign.token}'")
        _plot_first_keyframe(sign, args.save)


def _run_compare(args: argparse.Namespace) -> None:
    """Execute the compare subcommand.

    Args:
        args: Parsed arguments with ai_input, ref_input/ref_source, and report.
    """
    print(f"Loading AI signs from: {args.ai_input}")
    ai_raw = load_from_ai_output(args.ai_input)
    ai_signs = parse_signs(ai_raw)

    if args.ref_source == "mongodb":
        print("Loading reference signs from MongoDB...")
        ref_raw = load_from_mongodb()
    else:
        print(f"Loading reference signs from: {args.ref_input}")
        ref_raw = load_from_json(args.ref_input)

    ref_signs = parse_signs(ref_raw)

    print(f"Comparing {len(ai_signs)} AI sign(s) against {len(ref_signs)} reference(s)...")
    comparisons = compare_batch(ai_signs, ref_signs)

    print_comparison_summary(comparisons)

    if args.report:
        export_comparison_report(comparisons, args.report)


def _plot_first_keyframe(sign, save_path: str | None) -> None:
    """Plot the first keyframe of a sign as a static pose.

    Args:
        sign: The parsed sign to plot.
        save_path: Output file path or None for interactive display.
    """
    if not sign.keyframes:
        print("Error: Sign has no keyframes.")
        sys.exit(1)

    first_keyframe = sign.keyframes[0]
    left_angles = None
    right_angles = None

    if sign.arm in ("left", "both"):
        left_angles = servos_to_joint_angles(first_keyframe.left_servos, "left")
    if sign.arm in ("right", "both"):
        right_angles = servos_to_joint_angles(first_keyframe.right_servos, "right")

    plot_single_pose(
        joint_angles_left=left_angles,
        joint_angles_right=right_angles,
        title=sign.token,
        save_path=save_path,
    )
