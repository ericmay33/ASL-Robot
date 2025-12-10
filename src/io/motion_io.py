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
        print(f"[MOTION_IO] ❌ FATAL: Could not connect to any controller!")
        print(f"[MOTION_IO] Please check:")
        print(f"  - LEFT port: {left_port}")
        print(f"  - RIGHT port: {right_port}")
        print(f"  - Ensure ESP32 boards are connected and powered")
        print(f"  - Check if ports are already in use by another program")
        return

    def json_default(obj):
        if isinstance(obj, ObjectId):
            return str(obj)
        raise TypeError(f"Type {type(obj)} not serializable")

    print("[MOTION_IO] Started motion execution loop.")

    while True:
        file_io.motion_new_signal.wait()

        # Pop all motion scripts from the queue
        if not file_io.motion_queue.empty():
            script = file_io.pop_motion_script()
            payload = json.dumps(script, default=json_default) + "\n"
            payload_bytes = payload.encode("utf-8")

            # Send to both controllers simultaneously
            left_sent = False
            right_sent = False
            
            # Try to send to left controller
            if is_serial_valid(ser_left):
                try:
                    ser_left.write(payload_bytes)
                    ser_left.flush()
                    left_sent = True
                    print(f"[EXEC] Sent {script['token']} to LEFT controller.")
                except (serial.SerialException, OSError) as e:
                    print(f"[ERROR] Failed to send to LEFT controller: {e}")
                    print(f"[MOTION_IO] Attempting to reconnect LEFT controller...")
                    try:
                        if ser_left:
                            ser_left.close()
                    except:
                        pass
                    ser_left = connect_serial(left_port, baud, "LEFT")
            elif ser_left is None:
                # Try to reconnect if we haven't tried recently
                ser_left = connect_serial(left_port, baud, "LEFT")
            
            # Try to send to right controller
            if is_serial_valid(ser_right):
                try:
                    ser_right.write(payload_bytes)
                    ser_right.flush()
                    right_sent = True
                    print(f"[EXEC] Sent {script['token']} to RIGHT controller.")
                except (serial.SerialException, OSError) as e:
                    print(f"[ERROR] Failed to send to RIGHT controller: {e}")
                    print(f"[MOTION_IO] Attempting to reconnect RIGHT controller...")
                    try:
                        if ser_right:
                            ser_right.close()
                    except:
                        pass
                    ser_right = connect_serial(right_port, baud, "RIGHT")
            elif ser_right is None:
                # Try to reconnect if we haven't tried recently
                ser_right = connect_serial(right_port, baud, "RIGHT")

            # Wait for ACKs from both controllers (only if we sent to them)
            left_acked = not left_sent or ser_left is None
            right_acked = not right_sent or ser_right is None
            
            while not left_acked or not right_acked:
                # Check left controller
                if is_serial_valid(ser_left) and not left_acked:
                    try:
                        if ser_left.in_waiting > 0:
                            ack = ser_left.readline().decode(errors="ignore").strip()
                            if ack == "ACK":
                                print(f"[EXEC] LEFT controller: {script['token']} executed successfully.")
                                left_acked = True
                            elif ack != "":
                                print(f"[DEBUG] LEFT Arduino: {ack}")
                    except Exception as e:
                        print(f"[ERROR] Error reading from LEFT controller: {e}")
                elif not left_acked and not left_sent:
                    # If we didn't send, consider it acked
                    left_acked = True
                
                # Check right controller
                if is_serial_valid(ser_right) and not right_acked:
                    try:
                        if ser_right.in_waiting > 0:
                            ack = ser_right.readline().decode(errors="ignore").strip()
                            if ack == "ACK":
                                print(f"[EXEC] RIGHT controller: {script['token']} executed successfully.")
                                right_acked = True
                            elif ack != "":
                                print(f"[DEBUG] RIGHT Arduino: {ack}")
                    except Exception as e:
                        print(f"[ERROR] Error reading from RIGHT controller: {e}")
                elif not right_acked and not right_sent:
                    # If we didn't send, consider it acked
                    right_acked = True
                
                # Small delay to avoid busy waiting
                if not left_acked or not right_acked:
                    time.sleep(0.01)

            # Clear event if no motions left
            if file_io.motion_queue.empty():
                file_io.motion_new_signal.clear()

        time.sleep(0.01)