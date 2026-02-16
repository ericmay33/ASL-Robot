# src/io/motion_io.py
import json, serial, time, threading
from bson import ObjectId

# ACK timeout in seconds when waiting for Arduino to finish a motion
ACK_TIMEOUT = 8.0

# Smart delays: post-motion pause before sending the next command
# Fingerspelling (single letter): short delay for smooth letter-to-letter flow
# Full signs: longer delay for natural sign-to-sign pacing
FINGERSPELL_POST_DELAY = 0.03   # 30 ms between letters
SIGN_POST_DELAY = 0.15         # 150 ms between full signs

def connect_serial(port, baud, name):
    """Attempt to connect to a serial port with validation."""
    port = str(port).strip()

    try:
        ser = serial.Serial(port, baud, timeout=2)
        # Give the serial port a moment to initialize
        time.sleep(0.5)
        # Verify the port is actually open and configured
        if ser.is_open:
            # Clear any existing data in the buffer (if supported)
            try:
                ser.reset_input_buffer()
                ser.reset_output_buffer()
            except AttributeError:
                # Some platforms don't support reset_buffer methods
                try:
                    ser.flushInput()
                    ser.flushOutput()
                except:
                    pass
            print(f"[MOTION_IO] ✓ Connected to {name} controller at {port}")
            return ser
        else:
            print(f"[MOTION_IO] ⚠ {name} port opened but not configured: {port}")
            ser.close()
            return None
    except serial.SerialException as e:
        print(f"[MOTION_IO] ⚠ {name} controller connection failed: {e}")
        return None
    except Exception as e:
        print(f"[MOTION_IO] ⚠ {name} controller unexpected error: {e}")
        return None

def is_serial_valid(ser):
    """Check if a serial connection is still valid."""
    if ser is None:
        return False
    try:
        return ser.is_open and ser.writable
    except:
        return False

# Arm keys in keyframes: left controller uses L, LW, LE, LS; right uses R, RW, RE, RS
LEFT_ARM_KEYS = {"L", "LW", "LE", "LS"}
RIGHT_ARM_KEYS = {"R", "RW", "RE", "RS"}

def get_arms_for_script(script):
    """
    Inspect keyframes in the motion script and return which controller(s) need this command.
    Returns (send_to_left: bool, send_to_right: bool).
    Checks ALL keyframes. If keyframes are missing or empty, defaults to both arms (safe fallback).
    """
    send_to_left = False
    send_to_right = False
    keyframes = script.get("keyframes")
    if not keyframes or not isinstance(keyframes, (list, dict)):
        return True, True  # No keyframes or wrong type: send to both (safe fallback)
    frames = keyframes.values() if isinstance(keyframes, dict) else keyframes
    try:
        for frame in frames:
            if not isinstance(frame, dict):
                continue
            for key in frame:
                if key in LEFT_ARM_KEYS:
                    send_to_left = True
                if key in RIGHT_ARM_KEYS:
                    send_to_right = True
    except (TypeError, AttributeError):
        return True, True
    # If no arm keys found (e.g. only "time"), send to both
    if not send_to_left and not send_to_right:
        return True, True
    return send_to_left, send_to_right

def run_motion(file_io, left_port="COM3", right_port="COM6", baud=115200):
    # Connect to both controllers
    ser_left = connect_serial(left_port, baud, "LEFT")
    ser_right = connect_serial(right_port, baud, "RIGHT")
    
    if ser_left is None and ser_right is None:
        print(f"[MOTION_IO] ⚠ No controllers connected. Will continue without hardware.")
        print(f"[MOTION_IO] To connect controllers, ensure they're plugged in and ports are correct:")
        print(f"  - LEFT port: {left_port}")
        print(f"  - RIGHT port: {right_port}")

    REST_LEFT = {
        "token": "REST_LEFT",
        "type": "STATIC",
        "duration": 0.5,
        "keyframes": [{
            "time": 0.0,
            "L": [90, 90, 90, 90, 90],
            "LW": [90, 90],
            "LE": [90],
            "LS": [90, 90]
        }]
    }
    REST_RIGHT = {
        "token": "REST_RIGHT",
        "type": "STATIC",
        "duration": 0.5,
        "keyframes": [{
            "time": 0.0,
            "R": [90, 90, 90, 90, 90],
            "RW": [90, 90],
            "RE": [90],
            "RS": [90, 90]
        }]
    }

    def json_default(obj):
        if isinstance(obj, ObjectId):
            return str(obj)
        raise TypeError(f"Type {type(obj)} not serializable")

    print("[MOTION_IO] Started motion execution loop.")

    # Track last reconnection attempt to avoid spam
    last_reconnect_left = 0
    last_reconnect_right = 0
    reconnect_interval = 5.0  # Only try reconnecting every 5 seconds

    ack_received_left = threading.Event()
    ack_received_right = threading.Event()

    last_active_arm = None  # None, "both", "left", "right"

    def read_arduino_messages(ser, name, ack_event=None):
        """Non-blocking read of Arduino output. Sets ack_event when ACK is received."""
        if not is_serial_valid(ser):
            return
        try:
            while ser.in_waiting > 0:
                line = ser.readline().decode(errors="ignore").strip()
                if line and line == "ACK" and ack_event is not None:
                    ack_event.set()
        except (OSError, serial.SerialException, Exception):
            pass

    def wait_ack_then_send(ser, name, payload_bytes, ack_event, pending_ref, other_ser, other_name, other_ack_event, timeout_msg=None):
        """Wait for previous ACK if needed, send payload, drain. Returns (sent: bool, connection_lost: bool)."""
        if not is_serial_valid(ser):
            return (False, False)
        if pending_ref[0]:
            wait_start = time.time()
            while pending_ref[0] and not file_io.shutdown.is_set():
                read_arduino_messages(ser, name, ack_event)
                read_arduino_messages(other_ser, other_name, other_ack_event)
                if ack_event.is_set():
                    ack_event.clear()
                    pending_ref[0] = False
                    break
                if time.time() - wait_start > ACK_TIMEOUT:
                    if timeout_msg:
                        print(timeout_msg)
                    ack_event.clear()
                    pending_ref[0] = False
                    break
                time.sleep(0.01)
        if file_io.shutdown.is_set():
            return (False, False)
        try:
            ser.write(payload_bytes)
            ser.flush()
            pending_ref[0] = True
            time.sleep(0.05)
            read_arduino_messages(ser, name, ack_event)
            return (True, False)
        except (serial.SerialException, OSError) as e:
            print(f"[ERROR] Failed to send to {name} controller: {e}")
            try:
                ser.close()
            except Exception:
                pass
            return (False, True)

    pending_left = [False]
    pending_right = [False]

    while not file_io.shutdown.is_set():
        # Check for Arduino messages periodically (non-blocking)
        read_arduino_messages(ser_left, "LEFT", ack_received_left)
        read_arduino_messages(ser_right, "RIGHT", ack_received_right)

        # Wait for motion work (timeout so we can check shutdown)
        if not file_io.motion_new_signal.wait(timeout=0.1):
            continue

        # Pop all motion scripts from the queue (skip if shutting down)
        if not file_io.motion_queue.empty() and not file_io.shutdown.is_set():
            script = file_io.pop_motion_script()
            # Ensure keyframes is always an array for Arduino parsing
            if isinstance(script.get("keyframes"), dict):
                script["keyframes"] = list(script["keyframes"].values())
            payload = json.dumps(script, default=json_default) + "\n"
            payload_bytes = payload.encode("utf-8")
            current_time = time.time()

            send_to_left, send_to_right = get_arms_for_script(script)
            token_display = script.get("token", "?")
            target = "BOTH" if (send_to_left and send_to_right) else ("LEFT" if send_to_left else "RIGHT")
            print(f"[MOTION_IO] Sending '{token_display}' to {target}.")

            # Determine current active arm(s)
            if send_to_left and send_to_right:
                current_active_arm = "both"
            elif send_to_left:
                current_active_arm = "left"
            elif send_to_right:
                current_active_arm = "right"
            else:
                current_active_arm = None

            # Send rest to inactive arm when switching context (both→one arm or left↔right)
            if last_active_arm is not None and current_active_arm is not None:
                if current_active_arm == "right" and last_active_arm in ("both", "left"):
                    rest_script = dict(REST_LEFT)
                    if isinstance(rest_script.get("keyframes"), dict):
                        rest_script["keyframes"] = list(rest_script["keyframes"].values())
                    rest_bytes = (json.dumps(rest_script, default=json_default) + "\n").encode("utf-8")
                    sent, _ = wait_ack_then_send(
                        ser_left, "LEFT", rest_bytes, ack_received_left, pending_left,
                        ser_right, "RIGHT", ack_received_right, timeout_msg=None
                    )
                    if sent:
                        print("[MOTION_IO] Sending LEFT arm to rest position.")
                elif current_active_arm == "left" and last_active_arm in ("both", "right"):
                    rest_script = dict(REST_RIGHT)
                    if isinstance(rest_script.get("keyframes"), dict):
                        rest_script["keyframes"] = list(rest_script["keyframes"].values())
                    rest_bytes = (json.dumps(rest_script, default=json_default) + "\n").encode("utf-8")
                    sent, _ = wait_ack_then_send(
                        ser_right, "RIGHT", rest_bytes, ack_received_right, pending_right,
                        ser_left, "LEFT", ack_received_left, timeout_msg=None
                    )
                    if sent:
                        print("[MOTION_IO] Sending RIGHT arm to rest position.")

            # Send main script to left controller
            if send_to_left:
                sent, connection_lost = wait_ack_then_send(
                    ser_left, "LEFT", payload_bytes, ack_received_left, pending_left,
                    ser_right, "RIGHT", ack_received_right,
                    timeout_msg=f"[MOTION_IO] ⚠ ACK timeout from LEFT controller after {ACK_TIMEOUT}s (continuing anyway)."
                )
                if connection_lost:
                    ser_left = None
                    last_reconnect_left = current_time
                elif sent:
                    print(f"[EXEC] Sent {script['token']} to LEFT controller (duration: {script.get('duration', '?')}s).")
            if ser_left is None and (current_time - last_reconnect_left) >= reconnect_interval:
                ser_left = connect_serial(left_port, baud, "LEFT")
                if ser_left is None:
                    last_reconnect_left = current_time

            # Send main script to right controller
            if send_to_right:
                sent, connection_lost = wait_ack_then_send(
                    ser_right, "RIGHT", payload_bytes, ack_received_right, pending_right,
                    ser_left, "LEFT", ack_received_left,
                    timeout_msg=f"[MOTION_IO] ⚠ ACK timeout from RIGHT controller after {ACK_TIMEOUT}s (continuing anyway)."
                )
                if connection_lost:
                    ser_right = None
                    last_reconnect_right = current_time
                elif sent:
                    print(f"[EXEC] Sent {script['token']} to RIGHT controller (duration: {script.get('duration', '?')}s).")
            if ser_right is None and (current_time - last_reconnect_right) >= reconnect_interval:
                ser_right = connect_serial(right_port, baud, "RIGHT")
                if ser_right is None:
                    last_reconnect_right = current_time

            last_active_arm = current_active_arm

            # Inter-motion delay: shorter for letters, longer for full signs
            if not file_io.motion_queue.empty():
                delay_s = FINGERSPELL_POST_DELAY if len(script.get("token", "")) == 1 else SIGN_POST_DELAY
                time.sleep(delay_s)

            # Clear event if no motions left
            if file_io.motion_queue.empty():
                file_io.motion_new_signal.clear()

        time.sleep(0.01)

    # Shutdown: close serial ports
    for ser, name in [(ser_left, "LEFT"), (ser_right, "RIGHT")]:
        if ser is not None and is_serial_valid(ser):
            try:
                ser.close()
                print(f"[MOTION_IO] Closed {name} controller.")
            except Exception:
                pass
