"""
Modular sign-by-sign CLI: bypasses STT, AI worker thread, emotion UI, and DB worker thread.

Only MongoDB lookup / fingerspelling resolution and the motion serial thread run.

Usage:
    python -B -m src.testing.sign_demo [options]

Options:
    --gloss          Treat each input line as ASL gloss token(s), not English.
    --all-tokens     Queue every token from the line (default: first token only).
    --dry-run        Print motion JSON to stdout; do not connect serial or start motion thread.
    --left-port      Serial port for left arm (default: ASL_LEFT_PORT env or COM3).
    --right-port     Serial port for right arm (default: ASL_RIGHT_PORT env or COM6).

This module sets ASL_SIGN_DEMO=1 before other src imports so only MONGODB_URI and
MONGODB_DB_NAME are required in .env (see settings.validate).

English mode loads the Hugging Face T5 translate model on the first line you enter (slow).
Use --gloss for fast iteration when you know the DB token (see: python -m src.signs.listsigns).
"""
from __future__ import annotations

import argparse
import json
import os
import threading
import time
from typing import Any

# Must be set before any import that loads src.config.settings
os.environ["ASL_SIGN_DEMO"] = "1"

from bson import ObjectId

from src.database.db_connection import DatabaseConnection
from src.io.fileIO import FileIOManager
from src.io.motion_io import run_motion
from src.io.sign_resolution import enqueue_motions_for_token, motions_for_token

JOIN_TIMEOUT = 1.0
JOIN_MAX_WAIT = 8.0


def _json_default(obj: Any) -> str:
    if isinstance(obj, ObjectId):
        return str(obj)
    raise TypeError(f"Type {type(obj)} not serializable")


def _tokens_from_english(line: str) -> list[str]:
    from src.text_to_ASL.translate_AI import translate_to_asl_gloss

    return translate_to_asl_gloss(line)


def _print_help(gloss: bool, all_tokens: bool) -> None:
    print(
        "[SIGN_DEMO] Enter a line and press Enter to queue sign(s).\n"
        "  quit | exit | q  — exit\n"
        "  help             — this message\n"
        f"  Mode: {'gloss tokens' if gloss else 'English'}; "
        f"{'all tokens per line' if all_tokens else 'first token only'}.\n"
    )


def _process_line(
    line: str,
    file_io: FileIOManager,
    *,
    gloss: bool,
    all_tokens: bool,
    dry_run: bool,
) -> None:
    line = line.strip()
    if not line:
        return

    if gloss:
        parts = line.split()
        tokens = parts if all_tokens else parts[:1]
    else:
        tokens = _tokens_from_english(line)
        if not tokens:
            print("[SIGN_DEMO] Translation produced no tokens.")
            return
        tokens = tokens if all_tokens else tokens[:1]

    for token in tokens:
        if dry_run:
            print(f"[SIGN_DEMO] token={token!r} -> {len(motions_for_token(token))} motion script(s)")
            for m in motions_for_token(token):
                print(json.dumps(m, default=_json_default))
        else:
            enqueue_motions_for_token(file_io, token, log=True, log_tag="[SIGN_DEMO]")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="CLI sign demo: Mongo + motion thread only (no full robot pipeline).",
    )
    parser.add_argument(
        "--gloss",
        action="store_true",
        help="Input lines are ASL gloss token(s) (not English).",
    )
    parser.add_argument(
        "--all-tokens",
        action="store_true",
        help="Queue every token from the line instead of only the first.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print motion JSON only; do not start the motion / serial thread.",
    )
    parser.add_argument(
        "--left-port",
        default=os.getenv("ASL_LEFT_PORT", "COM3").strip(),
        help="Left arm serial port (default: ASL_LEFT_PORT or COM3).",
    )
    parser.add_argument(
        "--right-port",
        default=os.getenv("ASL_RIGHT_PORT", "COM6").strip(),
        help="Right arm serial port (default: ASL_RIGHT_PORT or COM6).",
    )
    args = parser.parse_args(argv)

    DatabaseConnection.initialize()
    file_io = FileIOManager()
    motion_thread: threading.Thread | None = None

    if not args.dry_run:
        motion_thread = threading.Thread(
            target=run_motion,
            args=(file_io,),
            kwargs={
                "left_port": args.left_port,
                "right_port": args.right_port,
            },
            daemon=False,
            name="motion",
        )
        motion_thread.start()
        print(
            f"[SIGN_DEMO] Motion thread started "
            f"(LEFT={args.left_port!r}, RIGHT={args.right_port!r})."
        )
    else:
        print("[SIGN_DEMO] Dry-run: printing motion JSON only.")

    if not args.gloss:
        print(
            "[SIGN_DEMO] English mode: the T5 model loads when you submit the first line "
            "(may take a while)."
        )

    _print_help(args.gloss, args.all_tokens)

    try:
        while True:
            try:
                line = input("sign> ")
            except EOFError:
                break
            cmd = line.strip().lower()
            if cmd in ("quit", "exit", "q"):
                break
            if cmd == "help":
                _print_help(args.gloss, args.all_tokens)
                continue
            _process_line(
                line,
                file_io,
                gloss=args.gloss,
                all_tokens=args.all_tokens,
                dry_run=args.dry_run,
            )
    except KeyboardInterrupt:
        print("\n[SIGN_DEMO] Interrupted.")

    file_io.shutdown.set()
    if motion_thread is not None and motion_thread.is_alive():
        w = 0.0
        while w < JOIN_MAX_WAIT and motion_thread.is_alive():
            motion_thread.join(timeout=JOIN_TIMEOUT)
            w += JOIN_TIMEOUT
        if motion_thread.is_alive():
            print("[SIGN_DEMO] Motion thread did not exit in time.")
    print("[SIGN_DEMO] Goodbye.")


if __name__ == "__main__":
    main()
