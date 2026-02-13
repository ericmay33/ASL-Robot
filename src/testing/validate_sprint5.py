"""
Sprint 5 Validation Script

Validates all Sprint 5 changes: code structure, configuration, STT factory,
motion pipeline, and dependencies. Static analysis only - no hardware or
audio streams.

Usage (from project root):
    python -m src.testing.validate_sprint5

On Windows, if you see UnicodeEncodeError for checkmarks, run:
    set PYTHONIOENCODING=utf-8
    python -m src.testing.validate_sprint5
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import List, Optional, Tuple

# Project root: parent of src/
_SCRIPT_DIR = Path(__file__).resolve().parent
_SRC_DIR = _SCRIPT_DIR.parent
_ROOT_DIR = _SRC_DIR.parent


def _env_path():
    """Path to .env at project root."""
    return _ROOT_DIR / ".env"


def _load_env_vars():
    """Load .env into os.environ if file exists. Return dict of key=value for checks."""
    env_file = _env_path()
    if not env_file.exists():
        return {}
    try:
        from dotenv import load_dotenv
        load_dotenv(env_file)
    except Exception:
        pass
    # Also parse manually so we can report "set" vs "missing" without dotenv
    result = {}
    try:
        with open(env_file, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, val = line.partition("=")
                    result[key.strip()] = val.strip().strip('"').strip("'")
    except OSError:
        pass
    return result


def run_code_structure_checks(results: list) -> None:
    """1. Code Structure Checks."""
    new_files = [
        _SRC_DIR / "speech_to_text" / "base_stt.py",
        _SRC_DIR / "speech_to_text" / "cloud_stt.py",
        _SRC_DIR / "speech_to_text" / "local_stt.py",
        _SRC_DIR / "speech_to_text" / "stt_factory.py",
    ]
    modified_files = [
        _SRC_DIR / "io" / "motion_io.py",
        _SRC_DIR / "io" / "db_io.py",
        _SRC_DIR / "io" / "stt_io.py",
    ]
    for p in new_files + modified_files:
        name = p.name
        if p.exists():
            results.append(("pass", f"Code structure: {name} exists", None))
        else:
            results.append(("fail", f"Code structure: {name} exists", f"File not found: {p}"))


def run_config_checks(results: list) -> None:
    """2. Configuration Checks."""
    env_file = _env_path()
    env_vars = _load_env_vars()

    if not env_file.exists():
        results.append(("fail", "Configuration: .env exists", ".env file not found"))
        results.append(("warn", "Configuration: STT_ENGINE", "Cannot check STT_ENGINE without .env"))
        return

    results.append(("pass", "Configuration: .env exists", None))

    stt_engine_raw = env_vars.get("STT_ENGINE") or os.getenv("STT_ENGINE") or ""
    stt_engine = stt_engine_raw.strip().lower() if stt_engine_raw else "cloud"

    if "STT_ENGINE" not in env_vars and not os.getenv("STT_ENGINE"):
        results.append(("warn", "Configuration: STT_ENGINE in .env", "STT_ENGINE not set in .env; default 'cloud' used"))
    else:
        results.append(("pass", "Configuration: STT_ENGINE in .env", None))

    if stt_engine not in ("cloud", "local"):
        results.append(("fail", "Configuration: STT_ENGINE valid", f"STT_ENGINE must be 'cloud' or 'local', got: {stt_engine!r}"))
    else:
        results.append(("pass", "Configuration: STT_ENGINE valid", None))

    if stt_engine == "cloud":
        creds_env = env_vars.get("GOOGLE_APPLICATION_CREDENTIALS") or os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        if not creds_env:
            results.append(("fail", "Configuration: cloud credentials path set", "GOOGLE_APPLICATION_CREDENTIALS not set"))
        else:
            creds_path = Path(creds_env)
            if not creds_path.is_absolute():
                creds_path = _ROOT_DIR / creds_env
            if creds_path.exists():
                results.append(("pass", "Configuration: cloud credentials file exists", None))
            else:
                results.append(("fail", "Configuration: cloud credentials file exists", f"File not found: {creds_path}"))

    if stt_engine == "local":
        model_set = "LOCAL_STT_MODEL" in env_vars or os.getenv("LOCAL_STT_MODEL") is not None
        device_set = "LOCAL_STT_DEVICE" in env_vars or os.getenv("LOCAL_STT_DEVICE") is not None
        if model_set and device_set:
            results.append(("pass", "Configuration: LOCAL_STT_MODEL and LOCAL_STT_DEVICE set", None))
        elif model_set or device_set:
            results.append(("warn", "Configuration: LOCAL_STT_MODEL and LOCAL_STT_DEVICE set", "One is set; defaults used for the other"))
        else:
            results.append(("warn", "Configuration: LOCAL_STT_MODEL and LOCAL_STT_DEVICE set", "Neither set; factory uses defaults (base, cpu)"))


def run_stt_factory_tests(results: list) -> None:
    """3. STT Factory Tests (import and create engines, no start)."""
    try:
        from src.speech_to_text.stt_factory import create_stt
        results.append(("pass", "STT Factory: import STTFactory (create_stt)", None))
    except Exception as e:
        results.append(("fail", "STT Factory: import STTFactory (create_stt)", str(e)))
        return

    # Create cloud engine (don't start)
    try:
        os.environ["STT_ENGINE"] = "cloud"
        from src.speech_to_text.stt_factory import create_stt
        from src.speech_to_text.base_stt import BaseSTT
        cloud_stt = create_stt()
        if isinstance(cloud_stt, BaseSTT):
            results.append(("pass", "STT Factory: create cloud engine inherits BaseSTT", None))
        else:
            results.append(("fail", "STT Factory: create cloud engine inherits BaseSTT", f"Expected BaseSTT, got {type(cloud_stt).__name__}"))
    except Exception as e:
        results.append(("fail", "STT Factory: create cloud engine", str(e)))

    # Create local engine (don't start)
    try:
        os.environ["STT_ENGINE"] = "local"
        from src.speech_to_text.stt_factory import create_stt
        from src.speech_to_text.base_stt import BaseSTT
        local_stt = create_stt()
        if isinstance(local_stt, BaseSTT):
            results.append(("pass", "STT Factory: create local engine inherits BaseSTT", None))
        else:
            results.append(("fail", "STT Factory: create local engine inherits BaseSTT", f"Expected BaseSTT, got {type(local_stt).__name__}"))
    except Exception as e:
        results.append(("fail", "STT Factory: create local engine", str(e)))


def run_motion_pipeline_tests(results: list) -> None:
    """4. Motion Pipeline Tests (source inspection only)."""
    motion_path = _SRC_DIR / "io" / "motion_io.py"
    db_path = _SRC_DIR / "io" / "db_io.py"

    if not motion_path.exists():
        results.append(("fail", "Motion pipeline: motion_io.py ACK variables", "motion_io.py not found"))
        return

    motion_src = motion_path.read_text(encoding="utf-8", errors="ignore")

    if "ack_received_left" in motion_src and "ack_received_right" in motion_src:
        results.append(("pass", "Motion pipeline: ACK tracking variables (ack_received_left/right)", None))
    else:
        results.append(("fail", "Motion pipeline: ACK tracking variables", "ack_received_left or ack_received_right not found in motion_io.py"))

    if "FINGERSPELL_POST_DELAY" in motion_src and "SIGN_POST_DELAY" in motion_src:
        results.append(("pass", "Motion pipeline: delay constants (FINGERSPELL_POST_DELAY, SIGN_POST_DELAY)", None))
    else:
        results.append(("fail", "Motion pipeline: delay constants", "FINGERSPELL_POST_DELAY or SIGN_POST_DELAY not found in motion_io.py"))

    if "def get_arms_for_script" in motion_src:
        results.append(("pass", "Motion pipeline: get_arms_for_script() exists", None))
    else:
        results.append(("fail", "Motion pipeline: get_arms_for_script()", "get_arms_for_script not found in motion_io.py"))

    if not db_path.exists():
        results.append(("fail", "Motion pipeline: db_io fallback no CODE check", "db_io.py not found"))
        return

    db_src = db_path.read_text(encoding="utf-8", errors="ignore")
    # Fallback should not check for "CODE" specifically (generalized fingerspelling)
    if 'token == "CODE"' in db_src or "token == 'CODE'" in db_src or '=="CODE"' in db_src or "=='CODE'" in db_src:
        results.append(("fail", "Motion pipeline: db_io fallback not CODE-specific", "db_io.py still checks for CODE specifically"))
    else:
        results.append(("pass", "Motion pipeline: db_io fallback not CODE-specific", None))


def run_dependency_checks(results: list) -> None:
    """5. Dependency Checks (import only)."""
    try:
        import whisper
        results.append(("pass", "Dependency: openai-whisper (import whisper)", None))
    except ImportError as e:
        results.append(("fail", "Dependency: openai-whisper (import whisper)", str(e)))

    try:
        import torch
        results.append(("pass", "Dependency: torch", None))
    except ImportError as e:
        results.append(("fail", "Dependency: torch", str(e)))

    try:
        import google.cloud.speech
        results.append(("pass", "Dependency: google-cloud-speech", None))
    except ImportError as e:
        results.append(("fail", "Dependency: google-cloud-speech", str(e)))


def _safe_symbols() -> Tuple[str, str, str]:
    """Return (pass_sym, fail_sym, warn_sym); use ASCII if UTF-8 symbols fail."""
    symbols = ("\u2705", "\u274c", "\u26a0\ufe0f ")  # ✅ ❌ ⚠️
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    try:
        enc = getattr(sys.stdout, "encoding", None) or "utf-8"
        (symbols[0] + " ").encode(enc)
    except (UnicodeEncodeError, LookupError):
        return ("[PASS]", "[FAIL]", "[WARN] ")
    return symbols


def main() -> int:
    pass_sym, fail_sym, warn_sym = _safe_symbols()

    results: List[Tuple[str, str, Optional[str]]] = []

    run_code_structure_checks(results)
    run_config_checks(results)
    run_stt_factory_tests(results)
    run_motion_pipeline_tests(results)
    run_dependency_checks(results)

    passed = sum(1 for r in results if r[0] == "pass")
    failed = sum(1 for r in results if r[0] == "fail")
    warnings = sum(1 for r in results if r[0] == "warn")

    for status, name, detail in results:
        if status == "pass":
            print(f"{pass_sym} PASS: {name}")
        elif status == "fail":
            print(f"{fail_sym} FAIL: {name}" + (f" - {detail}" if detail else ""))
        else:
            print(f"{warn_sym} WARN: {name}" + (f" - {detail}" if detail else ""))

    print()
    print("===================")
    print("SUMMARY")
    print(f"{pass_sym} Passed: {passed}")
    print(f"{fail_sym} Failed: {failed}")
    print(f"{warn_sym} Warnings: {warnings}")
    print("===================")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
