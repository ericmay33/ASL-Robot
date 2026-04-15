#!/usr/bin/env python3
"""
wRIST Hardware Test Suite
Interactive CLI for validating stepper and servo operation on the ASL robot arms.

Usage:
    python -m src.testing.test_hardware
"""

import json
import sys
import time

import serial

# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────
BAUD         = 115200
ACK_TIMEOUT  = 8.0   # seconds to wait for ACK after each command
BOOT_TIMEOUT = 5.0   # seconds to wait for "Ready" boot message on connect
STEP_PAUSE   = 0.5   # pause between commands so motion is visible

# ─────────────────────────────────────────────────────────────────────────────
# SERIAL HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def connect_arm(name: str) -> "serial.Serial | None":
    """Prompt for a COM port and attempt to connect. Returns Serial or None."""
    port = input(f"  {name} arm COM port (leave blank to skip): ").strip()
    if not port:
        print(f"  [{name}] Skipped.\n")
        return None
    try:
        ser = serial.Serial(port, BAUD, timeout=1)
        time.sleep(0.3)
        try:
            ser.reset_input_buffer()
            ser.reset_output_buffer()
        except AttributeError:
            pass
        print(f"  [{name}] Connected at {port}.\n")
        return ser
    except serial.SerialException as e:
        print(f"  [{name}] Failed to connect: {e}\n")
        return None


def wait_ready(ser: "serial.Serial", name: str, timeout: float = BOOT_TIMEOUT) -> bool:
    """
    Wait for the board's 'Ready' boot message.
    Returns True if received within timeout.
    If the board is already running (no boot message), continues anyway.
    """
    print(f"  [{name}] Waiting for boot message ({int(timeout)}s)...", end="", flush=True)
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            line = ser.readline().decode(errors="ignore").strip()
            if line:
                print(f"\n  [{name}] {line}")
            if "Ready" in line:
                return True
        except Exception:
            break
    print(f"\n  [{name}] No boot message — board may already be running, continuing.\n")
    return False


def drain(ser: "serial.Serial") -> None:
    """Discard any pending serial data before sending a command."""
    try:
        ser.reset_input_buffer()
    except Exception:
        pass


def send_and_wait(
    ser: "serial.Serial",
    description: str,
    payload: dict,
    timeout: float = ACK_TIMEOUT,
) -> tuple[bool, float]:
    """
    Send a JSON command and wait for ACK. Prints formatted output.
    Returns (passed: bool, elapsed_seconds: float).
    """
    raw = json.dumps(payload)
    print(f"\n[TEST] {description}")
    print(f"[SEND] {raw}")
    print(f"[WAIT] Waiting for ACK...", end="", flush=True)

    drain(ser)
    try:
        ser.write((raw + "\n").encode())
        ser.flush()
    except Exception as e:
        print(f"\n[FAIL] Write error: {e} ✗")
        return False, 0.0

    start = time.time()
    deadline = start + timeout
    while time.time() < deadline:
        try:
            line = ser.readline().decode(errors="ignore").strip()
            if line == "ACK":
                elapsed = time.time() - start
                print(f"\n[ACK]  Received in {elapsed:.2f}s ✓")
                return True, elapsed
        except Exception:
            break

    elapsed = time.time() - start
    print(f"\n[FAIL] No ACK received within {timeout}s ✗")
    return False, elapsed


def check_arm(ser: "serial.Serial | None", name: str) -> bool:
    """Return True if the serial connection is available, otherwise print an error."""
    if ser is None:
        print(f"\n[ERROR] {name} arm is not connected. Re-run and enter its COM port.\n")
        return False
    return True


def print_summary(test_name: str, results: list[bool]) -> None:
    passed = sum(results)
    total  = len(results)
    bar    = "=" * 44
    status = "ALL PASSED ✓" if passed == total else f"{passed}/{total} passed ✗"
    print(f"\n{bar}")
    print(f"  {test_name}: {passed}/{total} — {status}")
    print(f"{bar}\n")


# ─────────────────────────────────────────────────────────────────────────────
# TEST SEQUENCES
# ─────────────────────────────────────────────────────────────────────────────

def test_shoulder_rotation(ser: "serial.Serial", side: str, label: str) -> list[bool]:
    key = f"{side}S"
    results = []
    results.append(send_and_wait(
        ser, f"{label} Shoulder Rotation → 135°  (elevation stays neutral)",
        {"token": "TEST_ROT", "duration": 2.0, "keyframes": [{key: [135, 90]}]}
    )[0])
    time.sleep(STEP_PAUSE)
    results.append(send_and_wait(
        ser, f"{label} Shoulder Rotation → 90°   (return to neutral)",
        {"token": "TEST_ROT", "duration": 2.0, "keyframes": [{key: [90, 90]}]}
    )[0])
    print_summary(f"{label} Shoulder Rotation", results)
    return results


def test_shoulder_elevation(ser: "serial.Serial", side: str, label: str) -> list[bool]:
    key = f"{side}S"
    results = []
    results.append(send_and_wait(
        ser, f"{label} Shoulder Elevation → 135°  (rotation stays neutral)",
        {"token": "TEST_ELEV", "duration": 2.0, "keyframes": [{key: [90, 135]}]}
    )[0])
    time.sleep(STEP_PAUSE)
    results.append(send_and_wait(
        ser, f"{label} Shoulder Elevation → 90°   (return to neutral)",
        {"token": "TEST_ELEV", "duration": 2.0, "keyframes": [{key: [90, 90]}]}
    )[0])
    print_summary(f"{label} Shoulder Elevation", results)
    return results


def test_shoulder_combined(ser: "serial.Serial", side: str, label: str) -> list[bool]:
    key = f"{side}S"
    steps = [
        (f"{label} Shoulder Combined → [135°, 135°]",              [135, 135]),
        (f"{label} Shoulder Combined → [45°, 135°]",               [45, 135]),
        (f"{label} Shoulder Combined → [90°, 90°] (return to neutral)", [90, 90]),
    ]
    results = []
    for desc, angles in steps:
        results.append(send_and_wait(
            ser, desc,
            {"token": "TEST_COMB", "duration": 2.0, "keyframes": [{key: angles}]}
        )[0])
        time.sleep(STEP_PAUSE)
    print_summary(f"{label} Shoulder Combined", results)
    return results


def test_hand(ser: "serial.Serial", side: str, label: str) -> list[bool]:
    key     = side   # "L" or "R"
    fingers = ["Thumb", "Index", "Middle", "Ring", "Pinky"]
    neutral = [90, 90, 90, 90, 90]
    results = []

    for i, finger in enumerate(fingers):
        target = neutral.copy()
        target[i] = 180
        results.append(send_and_wait(
            ser, f"{label} Hand — {finger} → 180°",
            {"token": "TEST_HAND", "duration": 1.0, "keyframes": [{key: target}]}
        )[0])
        time.sleep(STEP_PAUSE)
        results.append(send_and_wait(
            ser, f"{label} Hand — {finger} → 90° (return)",
            {"token": "TEST_HAND", "duration": 1.0, "keyframes": [{key: neutral}]}
        )[0])
        time.sleep(STEP_PAUSE)

    # All fingers together
    results.append(send_and_wait(
        ser, f"{label} Hand — All fingers → 180°",
        {"token": "TEST_HAND", "duration": 1.0, "keyframes": [{key: [180] * 5}]}
    )[0])
    time.sleep(STEP_PAUSE)
    results.append(send_and_wait(
        ser, f"{label} Hand — All fingers → 90° (return)",
        {"token": "TEST_HAND", "duration": 1.0, "keyframes": [{key: neutral}]}
    )[0])

    print_summary(f"{label} Hand Servos", results)
    return results


def test_wrist(ser: "serial.Serial", side: str, label: str) -> list[bool]:
    key   = f"{side}W"
    steps = [
        (f"{label} Wrist Rotation → 45°",           [45,  90]),
        (f"{label} Wrist Rotation → 135°",          [135, 90]),
        (f"{label} Wrist Flexion  → 45°",           [90,  45]),
        (f"{label} Wrist Flexion  → 135°",          [90, 135]),
        (f"{label} Wrist → center [90°, 90°] (return)", [90, 90]),
    ]
    results = []
    for desc, angles in steps:
        results.append(send_and_wait(
            ser, desc,
            {"token": "TEST_WRIST", "duration": 1.5, "keyframes": [{key: angles}]}
        )[0])
        time.sleep(STEP_PAUSE)
    print_summary(f"{label} Wrist Servos", results)
    return results


def test_elbow(ser: "serial.Serial", side: str, label: str) -> list[bool]:
    key   = f"{side}E"
    steps = [
        (f"{label} Elbow → 45°",          [45]),
        (f"{label} Elbow → 135°",         [135]),
        (f"{label} Elbow → 90° (return)", [90]),
    ]
    results = []
    for desc, angles in steps:
        results.append(send_and_wait(
            ser, desc,
            {"token": "TEST_ELBOW", "duration": 1.5, "keyframes": [{key: angles}]}
        )[0])
        time.sleep(STEP_PAUSE)
    print_summary(f"{label} Elbow", results)
    return results


def test_full_arm(ser: "serial.Serial", side: str, label: str) -> None:
    bar = "=" * 44
    print(f"\n{bar}")
    print(f"  FULL {label.upper()} ARM TEST — all joints in sequence")
    print(bar)
    all_results: list[bool] = []
    all_results += test_hand(ser, side, label)
    all_results += test_wrist(ser, side, label)
    all_results += test_elbow(ser, side, label)
    all_results += test_shoulder_rotation(ser, side, label)
    all_results += test_shoulder_elevation(ser, side, label)
    all_results += test_shoulder_combined(ser, side, label)
    passed = sum(all_results)
    total  = len(all_results)
    status = "ALL PASSED ✓" if passed == total else f"{passed}/{total} passed ✗"
    print(f"\n{bar}")
    print(f"  FULL {label.upper()} ARM TOTAL: {passed}/{total} — {status}")
    print(f"{bar}\n")


def custom_command(
    ser_left:  "serial.Serial | None",
    ser_right: "serial.Serial | None",
) -> None:
    raw = input("\nEnter raw JSON command: ").strip()
    if not raw:
        return
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"[ERROR] Invalid JSON: {e}")
        return

    target = input("Send to which arm? [L]eft / [R]ight / [B]oth: ").strip().upper()
    pairs: list[tuple["serial.Serial", str]] = []
    if target in ("L", "B"):
        if ser_left:
            pairs.append((ser_left, "LEFT"))
        else:
            print("[ERROR] Left arm not connected.")
    if target in ("R", "B"):
        if ser_right:
            pairs.append((ser_right, "RIGHT"))
        else:
            print("[ERROR] Right arm not connected.")

    for ser, name in pairs:
        send_and_wait(ser, f"Custom → {name}", payload)


# ─────────────────────────────────────────────────────────────────────────────
# MENU
# ─────────────────────────────────────────────────────────────────────────────

MENU = """
=== wRIST Hardware Test Suite ===
  1.  Test Left  Shoulder Rotation
  2.  Test Left  Shoulder Elevation
  3.  Test Left  Shoulder Combined
  4.  Test Right Shoulder Rotation
  5.  Test Right Shoulder Elevation
  6.  Test Right Shoulder Combined
  7.  Test Left  Hand Servos
  8.  Test Right Hand Servos
  9.  Test Left  Wrist Servos
  10. Test Right Wrist Servos
  11. Test Left  Elbow
  12. Test Right Elbow
  13. Full Left  Arm Test (all joints)
  14. Full Right Arm Test (all joints)
  15. Custom Command (raw JSON)
  0.  Exit
"""

_DISPATCH = {
    "1":  lambda L, R: check_arm(L, "Left")  and test_shoulder_rotation(L, "L", "Left"),
    "2":  lambda L, R: check_arm(L, "Left")  and test_shoulder_elevation(L, "L", "Left"),
    "3":  lambda L, R: check_arm(L, "Left")  and test_shoulder_combined(L, "L", "Left"),
    "4":  lambda L, R: check_arm(R, "Right") and test_shoulder_rotation(R, "R", "Right"),
    "5":  lambda L, R: check_arm(R, "Right") and test_shoulder_elevation(R, "R", "Right"),
    "6":  lambda L, R: check_arm(R, "Right") and test_shoulder_combined(R, "R", "Right"),
    "7":  lambda L, R: check_arm(L, "Left")  and test_hand(L, "L", "Left"),
    "8":  lambda L, R: check_arm(R, "Right") and test_hand(R, "R", "Right"),
    "9":  lambda L, R: check_arm(L, "Left")  and test_wrist(L, "L", "Left"),
    "10": lambda L, R: check_arm(R, "Right") and test_wrist(R, "R", "Right"),
    "11": lambda L, R: check_arm(L, "Left")  and test_elbow(L, "L", "Left"),
    "12": lambda L, R: check_arm(R, "Right") and test_elbow(R, "R", "Right"),
    "13": lambda L, R: check_arm(L, "Left")  and test_full_arm(L, "L", "Left"),
    "14": lambda L, R: check_arm(R, "Right") and test_full_arm(R, "R", "Right"),
    "15": lambda L, R: custom_command(L, R),
}


def main() -> None:
    print("\n=== wRIST Hardware Test Suite — Setup ===")
    ser_left  = connect_arm("LEFT")
    ser_right = connect_arm("RIGHT")

    if ser_left is None and ser_right is None:
        print("[ERROR] No arms connected. Exiting.")
        sys.exit(1)

    if ser_left:
        wait_ready(ser_left, "LEFT")
    if ser_right:
        wait_ready(ser_right, "RIGHT")

    while True:
        print(MENU)
        try:
            choice = input("Select option: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nInterrupted. Exiting.")
            break

        if choice == "0":
            print("Exiting.")
            break
        elif choice in _DISPATCH:
            _DISPATCH[choice](ser_left, ser_right)
        else:
            print("  Invalid option — enter a number from 0 to 15.\n")

    for ser, name in [(ser_left, "LEFT"), (ser_right, "RIGHT")]:
        if ser and ser.is_open:
            try:
                ser.close()
                print(f"[INFO] {name} serial port closed.")
            except Exception:
                pass


if __name__ == "__main__":
    main()
