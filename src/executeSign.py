import serial, time, os
from src.database.db_connection import DatabaseConnection
from src.database.db_functions import get_sign_by_token

# --- CONFIG ---
ESP32_PORT = "/dev/tty.usbserial-0001"   # Change to your actual port
BAUD_RATE = 115200
INSTRUCTIONS_FILE = "OutputFiles/gemini_output_log.txt"

# --- INIT ---
DatabaseConnection.initialize()
ser = serial.Serial(ESP32_PORT, BAUD_RATE, timeout=1)
time.sleep(2)
print("[EXECUTOR] Connected to ESP32")

def send_keyframe(angles):
    """Send a list of servo angles to the ESP32."""
    msg = ",".join(map(str, angles)) + "\n"
    ser.write(msg.encode())
    print(f"Sent → {msg.strip()}")

    while True:
        line = ser.readline().decode().strip()
        if line:
            print(f"Received ← {line}")
            if "ACK" in line:
                break

def execute_sign(sign_data):
    """Play the sign's keyframes sequentially."""
    keyframes = sign_data.get("keyframes", [])
    duration = sign_data.get("duration", 1.0)
    if not keyframes:
        print("[WARN] No keyframes for sign.")
        return

    for frame in keyframes:
        send_keyframe(frame["L"])   # For now, only left hand
        time.sleep(0.3)             # small delay between frames
    print(f"[DONE] Finished sign: {sign_data['token']}\n")

def watch_for_new_tokens():
    """Continuously watch output.txt for new lines."""
    print(f"[WATCHING] {INSTRUCTIONS_FILE}")
    seen_lines = set()

    while True:
        if not os.path.exists(INSTRUCTIONS_FILE):
            time.sleep(1)
            continue

        with open(INSTRUCTIONS_FILE, "r", encoding="utf-8") as f:
            lines = [line.strip().upper() for line in f if line.strip()]

        for token in lines:
            if token not in seen_lines:
                print(f"\n[NEW TOKEN] {token}")
                seen_lines.add(token)
                sign_data = get_sign_by_token(token)
                if sign_data:
                    execute_sign(sign_data)
                else:
                    print(f"[WARN] Token '{token}' not found in DB.")
        time.sleep(1)

if __name__ == "__main__":
    try:
        watch_for_new_tokens()
    except KeyboardInterrupt:
        ser.close()
        print("\n[EXECUTOR] Stopped.")
