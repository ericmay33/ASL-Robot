# src/io/motion_io.py
import json
import serial
import time
from bson import ObjectId
from src.database.db_functions import get_sign_by_token
from src.database.db_connection import DatabaseConnection

def run_motion(file_io, port="/dev/cu.usbmodem1201", baud=115200):
    try:
        ser = serial.Serial(port, baud, timeout=2)
        print(f"[MOTION] Connected to {port}")
    except Exception as e:
        print(f"[MOTION] Serial connection failed: {e}")
        return

    # Helper function for JSON serialization
    def json_default(obj):
        if isinstance(obj, ObjectId):
            return str(obj)
        raise TypeError(f"Type {type(obj)} not serializable")

    while True:
        # Get token from AI output
        token = file_io.pop_asl_token()
        if not token:
            time.sleep(0.05)
            continue

        # Fetch sign data
        sign_data = get_sign_by_token(token)
        if not sign_data:
            print(f"[WARN] Token '{token}' not found in DB.")
            continue

        # Push to motion queue
        file_io.push_motion_script(sign_data)
        print(f"[MOTION] Queued motion for {token}")

        # Send when ready (acts as fixed-size buffer)
        script = file_io.pop_motion_script()
        if script:
            print(f"[EXEC] Sending {script['token']} to Arduino...")
            ser.write((json.dumps(script, default=json_default) + "\n").encode("utf-8"))
            ser.flush()

            # Wait until Arduino sends "ACK"
            while True:
                ack = ser.readline().decode(errors="ignore").strip()
                if ack == "ACK":
                    print(f"[EXEC] {script['token']} executed successfully.")
                    break
                elif ack != "":
                    print(f"[DEBUG] Arduino response: {ack}")
                    