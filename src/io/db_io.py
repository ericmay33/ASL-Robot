from src.database.db_connection import DatabaseConnection
from src.database.db_functions import get_sign_by_token
from src.cache.fingerspelling_cache import get_letter_motion
import time

#configs
NONEXIST_TOKENS_FILE = "src/database/tokens_to_add.txt"

def run_database(file_io):
    DatabaseConnection.initialize()
    print("[DB_IO] Started database I/O handler loop.")

    while True:
        # Wait for tokens from AI_IO
        file_io.asl_new_signal.wait()
        
        # Process all tokens in the queue
        while not file_io.asl_token_queue.empty():
            token = file_io.pop_asl_token()
            sign_data = get_sign_by_token(token)

            if sign_data:
                file_io.push_motion_script(sign_data)
                print(f"[DB_IO] Retrieved sign for {token}")
                continue

            # If not in DB → fallback to fingerspelling
            print(f"[DB_IO] Token '{token}' not in DB. Using fallback.")

            if (token == "CODE"):
                for char in token:
                    motion = get_letter_motion(char)
                    if motion:
                        file_io.push_motion_script(motion)
                        print(f"[DB_IO] Queued letter '{char}' from fallback cache.")
                    else:
                        print(f"[DB_IO] Letter '{char}' not available.")

        # Reset event after processing all tokens
        file_io.asl_new_signal.clear()

        # Reduce thread load
        time.sleep(0.01)