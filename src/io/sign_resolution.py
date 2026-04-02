"""Resolve ASL gloss tokens to motion script documents (DB or fingerspelling)."""

from __future__ import annotations

from src.cache.fingerspelling_cache import get_letter_motion
from src.database.db_functions import get_sign_by_token


def motions_for_token(token: str) -> list[dict]:
    """Return motion documents for one token without queueing (for dry-run / inspection)."""
    sign_data = get_sign_by_token(token)
    if sign_data:
        return [sign_data]
    token_str = (token or "").strip()
    if not token_str:
        return []
    out: list[dict] = []
    for char in token_str.upper():
        motion = get_letter_motion(char)
        if motion:
            out.append(motion)
    return out


def enqueue_motions_for_token(
    file_io,
    token: str,
    *,
    log: bool = True,
    log_tag: str = "[DB_IO]",
) -> int:
    """
    Push motion script(s) for one ASL token onto file_io.motion_queue.
    Returns the number of scripts queued.
    """
    sign_data = get_sign_by_token(token)
    if sign_data:
        file_io.push_motion_script(sign_data)
        if log:
            print(f"{log_tag} Retrieved sign for {token}")
        return 1

    token_str = (token or "").strip()
    if not token_str:
        return 0

    if log:
        print(f"{log_tag} Token '{token}' not in DB. Fallback fingerspelling.")
    queued = 0
    for char in token_str.upper():
        motion = get_letter_motion(char)
        if motion:
            file_io.push_motion_script(motion)
            queued += 1
            if log:
                print(f"{log_tag} Queued letter '{char}' (fallback fingerspelling).")
        elif log:
            print(f"{log_tag} Skipped '{char}' (no fingerspelling motion available).")
    if queued and log:
        print(f"{log_tag} Fallback fingerspelling: '{token_str}' -> {queued} letter(s) queued.")
    return queued
