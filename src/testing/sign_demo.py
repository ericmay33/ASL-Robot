"""
Modular sign-by-sign CLI: bypasses STT, AI translation, emotion UI, and DB worker thread.

Each input line is split on whitespace; each piece is queued as a MongoDB token
(case-insensitive — `hello` and `HELLO` resolve the same document). Unknown tokens
fall back to character-by-character fingerspelling. Bilateral signs (keyframes with
both L*/R* keys) are routed to both ESP32s automatically by motion_io.

Usage:
    python -B -m src.testing.sign_demo [options]

Options:
    --dry-run        Print motion JSON to stdout; do not connect serial or start motion thread.
    --left-port      Serial port for left arm (default: ASL_LEFT_PORT env or COM3).
    --right-port     Serial port for right arm (default: ASL_RIGHT_PORT env or COM4).

This module sets ASL_SIGN_DEMO=1 before other src imports so only MONGODB_URI and
MONGODB_DB_NAME are required in .env (see settings.validate).
"""
from __future__ import annotations

import argparse
import json
import os
import threading
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


def _print_help() -> None:
    print(
        "[SIGN_DEMO] Enter one or more space-separated tokens and press Enter.\n"
        "  e.g.  HELLO            -> one sign\n"
        "        hello friend     -> two signs (case-insensitive)\n"
        "        XYZ              -> unknown token: fingerspells X, Y, Z\n"
        "  quit | exit | q   - exit\n"
        "  help              - this message\n"
    )


def _process_line(line: str, file_io: FileIOManager, *, dry_run: bool) -> None:
    tokens = line.split()
    if not tokens:
        return
    for token in tokens:
        if dry_run:
            scripts = motions_for_token(token)
            print(f"[SIGN_DEMO] token={token!r} -> {len(scripts)} motion script(s)")
            for m in scripts:
                print(json.dumps(m, default=_json_default))
        else:
            enqueue_motions_for_token(file_io, token, log=True, log_tag="[SIGN_DEMO]")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="CLI sign demo: Mongo + motion thread only (no STT, no AI translation).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print motion JSON only; do not start the motion / serial thread.",
    )
    parser.add_argument(
        "--left-port",
        default=os.getenv("ASL_LEFT_PORT", "COM8").strip(),
        help="Left arm serial port (default: ASL_LEFT_PORT or COM3).",
    )
    parser.add_argument(
        "--right-port",
        default=os.getenv("ASL_RIGHT_PORT", "COM4").strip(),
        help="Right arm serial port (default: ASL_RIGHT_PORT or COM4).",
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

    _print_help()

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
                _print_help()
                continue
            _process_line(line, file_io, dry_run=args.dry_run)
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
