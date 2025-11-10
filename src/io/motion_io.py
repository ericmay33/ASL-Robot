# src/io/motion_io.py
import json, serial, time
from bson import ObjectId

def run_motion(file_io, port="/dev/cu.usbmodem11201", baud=115200):
    try:
        ser = serial.Serial(port, baud, timeout=2)
        print(f"[MOTION_IO] Connected to {port}")
    except Exception as e:
        print(f"[MOTION_IO] Serial connection failed: {e}")
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

            try:
                ser.write(payload.encode("utf-8"))
                ser.flush()
                print(f"[EXEC] Sent {script['token']} to Arduino.")
            except Exception as e:
                print(f"[ERROR] Failed to send motion: {e}")
                continue

            # Wait for ACK before continuing
            while True:
                ack = ser.readline().decode(errors="ignore").strip()
                if ack == "ACK":
                    print(f"[EXEC] {script['token']} executed successfully.")
                    break
                elif ack != "":
                    print(f"[DEBUG] Arduino: {ack}")

            # Clear event if no motions left
            if file_io.motion_queue.empty():
                file_io.motion_new_signal.clear()

        time.sleep(0.01)