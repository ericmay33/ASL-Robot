# src/io/motion_io.py
import json, serial, time, os
from bson import ObjectId

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

def run_motion(file_io, left_port="/dev/cu.usbserial-11240", right_port="/dev/cu.usbserial-11230", baud=115200):
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

    def read_arduino_messages(ser, name):
        """Non-blocking read of Arduino debug messages"""
        if not is_serial_valid(ser):
            return
        try:
            while ser.in_waiting > 0:
                line = ser.readline().decode(errors="ignore").strip()
                if line:
                    if line == "ACK":
                        # ACK is handled separately if needed
                        pass
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
        read_arduino_messages(ser_left, "LEFT")
        read_arduino_messages(ser_right, "RIGHT")
        
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
            
            # Try to send to left controller
            if is_serial_valid(ser_left):
                try:
                    ser_left.write(payload_bytes)
                    ser_left.flush()
                    print(f"[EXEC] Sent {script['token']} to LEFT controller (duration: {script.get('duration', '?')}s).")
                    
                    # Check for immediate response
                    time.sleep(0.1)  # Small delay to let Arduino process
                    read_arduino_messages(ser_left, "LEFT")
                    
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
            
            # Try to send to right controller
            if is_serial_valid(ser_right):
                try:
                    ser_right.write(payload_bytes)
                    ser_right.flush()
                    print(f"[EXEC] Sent {script['token']} to RIGHT controller (duration: {script.get('duration', '?')}s).")
                    
                    # Check for immediate response
                    time.sleep(0.1)  # Small delay to let Arduino process
                    read_arduino_messages(ser_right, "RIGHT")
                    
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
            
            # Add a small delay before processing next command to prevent queue overflow
            # This gives the Arduino time to start processing before we send the next command
            sign_duration = script.get('duration', 2.0)
            time.sleep(min(0.2, sign_duration * 0.1))  # Small delay, max 200ms

            # Clear event if no motions left
            if file_io.motion_queue.empty():
                file_io.motion_new_signal.clear()

        time.sleep(0.01)