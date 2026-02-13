# src/io/motion_io.py
import json, serial, time, os, threading
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
    if not os.path.exists(port):
        print(f"[MOTION_IO] ⚠ {name} port does not exist: {port}")
        return None
    
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

def run_motion(file_io, left_port="COM4", right_port="COM6", baud=115200):
    # Connect to both controllers
    ser_left = connect_serial(left_port, baud, "LEFT")
    ser_right = connect_serial(right_port, baud, "RIGHT")
    
    if ser_left is None and ser_right is None:
        print(f"[MOTION_IO] ⚠ No controllers connected. Will continue without hardware.")
        print(f"[MOTION_IO] To connect controllers, ensure they're plugged in and ports are correct:")
        print(f"  - LEFT port: {left_port}")
        print(f"  - RIGHT port: {right_port}")

    def json_default(obj):
        if isinstance(obj, ObjectId):
            return str(obj)
        raise TypeError(f"Type {type(obj)} not serializable")

    print("[MOTION_IO] Started motion execution loop.")

    # Track last reconnection attempt to avoid spam
    last_reconnect_left = 0
    last_reconnect_right = 0
    reconnect_interval = 5.0  # Only try reconnecting every 5 seconds

    # ACK-based synchronization: each arm has an event set when it sends ACK
    ack_received_left = threading.Event()
    ack_received_right = threading.Event()
    pending_ack_left = False
    pending_ack_right = False

    def read_arduino_messages(ser, name, ack_event=None):
        """Non-blocking read of Arduino debug messages. Sets ack_event when ACK is received."""
        if not is_serial_valid(ser):
            return
        try:
            while ser.in_waiting > 0:
                line = ser.readline().decode(errors="ignore").strip()
                if line:
                    if line == "ACK":
                        if ack_event is not None:
                            ack_event.set()
                        print(f"[MOTION_IO] ACK received from {name} controller.")
                    else:
                        print(f"[DEBUG] {name} Arduino: {line}")
        except (OSError, serial.SerialException) as e:
            # Device disconnected - this is expected, don't spam
            pass
        except Exception as e:
            # Other errors - log occasionally
            pass

    while True:
        # Check for Arduino messages periodically (non-blocking)
        read_arduino_messages(ser_left, "LEFT", ack_received_left)
        read_arduino_messages(ser_right, "RIGHT", ack_received_right)
        
        file_io.motion_new_signal.wait()

        # Pop all motion scripts from the queue
        if not file_io.motion_queue.empty():
            script = file_io.pop_motion_script()
            payload = json.dumps(script, default=json_default) + "\n"
            payload_bytes = payload.encode("utf-8")

            current_time = time.time()
            
            # Debug: Check queue size
            queue_size = file_io.motion_queue.qsize()
            if queue_size > 0:
                print(f"[DEBUG] Motion queue has {queue_size} remaining items")

            # Route command only to controller(s) whose arm keys appear in keyframes
            send_to_left, send_to_right = get_arms_for_script(script)
            token_display = script.get("token", "?")
            if send_to_left and send_to_right:
                print(f"[MOTION_IO] Routing '{token_display}' to BOTH controllers.")
            elif send_to_left:
                print(f"[MOTION_IO] Routing '{token_display}' to LEFT controller only.")
            elif send_to_right:
                print(f"[MOTION_IO] Routing '{token_display}' to RIGHT controller only.")
            else:
                print(f"[MOTION_IO] Routing '{token_display}' to BOTH (no arm keys in keyframes).")
            
            # Try to send to left controller (only if script uses left arm keys)
            if send_to_left and is_serial_valid(ser_left):
                # Wait for previous command's ACK before sending next (with timeout)
                if pending_ack_left:
                    wait_start = time.time()
                    while pending_ack_left:
                        read_arduino_messages(ser_left, "LEFT", ack_received_left)
                        read_arduino_messages(ser_right, "RIGHT", ack_received_right)
                        if ack_received_left.is_set():
                            ack_received_left.clear()
                            pending_ack_left = False
                            break
                        if time.time() - wait_start > ACK_TIMEOUT:
                            print(f"[MOTION_IO] ⚠ ACK timeout from LEFT controller after {ACK_TIMEOUT}s (continuing anyway).")
                            ack_received_left.clear()
                            pending_ack_left = False
                            break
                        time.sleep(0.01)
                try:
                    ser_left.write(payload_bytes)
                    ser_left.flush()
                    pending_ack_left = True
                    print(f"[EXEC] Sent {script['token']} to LEFT controller (duration: {script.get('duration', '?')}s).")
                    
                    # Drain any immediate response (ACK will be handled in next wait or periodic read)
                    time.sleep(0.05)
                    read_arduino_messages(ser_left, "LEFT", ack_received_left)
                    
                except (serial.SerialException, OSError) as e:
                    # Connection lost - show error and mark for reconnection
                    print(f"[ERROR] Failed to send to LEFT controller: {e}")
                    try:
                        ser_left.close()
                    except:
                        pass
                    ser_left = None
                    last_reconnect_left = current_time
            elif ser_left is None:
                # Only try reconnecting if enough time has passed
                if (current_time - last_reconnect_left) >= reconnect_interval:
                    ser_left = connect_serial(left_port, baud, "LEFT")
                    if ser_left is None:
                        last_reconnect_left = current_time
            
            # Try to send to right controller (only if script uses right arm keys)
            if send_to_right and is_serial_valid(ser_right):
                # Wait for previous command's ACK before sending next (with timeout)
                if pending_ack_right:
                    wait_start = time.time()
                    while pending_ack_right:
                        read_arduino_messages(ser_left, "LEFT", ack_received_left)
                        read_arduino_messages(ser_right, "RIGHT", ack_received_right)
                        if ack_received_right.is_set():
                            ack_received_right.clear()
                            pending_ack_right = False
                            break
                        if time.time() - wait_start > ACK_TIMEOUT:
                            print(f"[MOTION_IO] ⚠ ACK timeout from RIGHT controller after {ACK_TIMEOUT}s (continuing anyway).")
                            ack_received_right.clear()
                            pending_ack_right = False
                            break
                        time.sleep(0.01)
                try:
                    ser_right.write(payload_bytes)
                    ser_right.flush()
                    pending_ack_right = True
                    print(f"[EXEC] Sent {script['token']} to RIGHT controller (duration: {script.get('duration', '?')}s).")
                    
                    # Drain any immediate response (ACK will be handled in next wait or periodic read)
                    time.sleep(0.05)
                    read_arduino_messages(ser_right, "RIGHT", ack_received_right)
                    
                except (serial.SerialException, OSError) as e:
                    # Connection lost - show error and mark for reconnection
                    print(f"[ERROR] Failed to send to RIGHT controller: {e}")
                    try:
                        ser_right.close()
                    except:
                        pass
                    ser_right = None
                    last_reconnect_right = current_time
            elif ser_right is None:
                # Only try reconnecting if enough time has passed
                if (current_time - last_reconnect_right) >= reconnect_interval:
                    ser_right = connect_serial(right_port, baud, "RIGHT")
                    if ser_right is None:
                        last_reconnect_right = current_time
            
            # Timing is ACK-based: we wait for each arm's ACK before sending the next command to that arm.
            # Apply smart delay before next motion: short for fingerspelling, normal for full signs.
            if not file_io.motion_queue.empty():
                token = script.get("token", "")
                is_fingerspelling = len(token) == 1
                if is_fingerspelling:
                    delay_s = FINGERSPELL_POST_DELAY
                    print(f"[MOTION_IO] Fingerspelling delay: {int(delay_s * 1000)}ms before next motion.")
                else:
                    delay_s = SIGN_POST_DELAY
                    print(f"[MOTION_IO] Sign delay: {int(delay_s * 1000)}ms before next motion.")
                time.sleep(delay_s)

            # Clear event if no motions left
            if file_io.motion_queue.empty():
                file_io.motion_new_signal.clear()

        time.sleep(0.01)