from src.database.db_connection import DatabaseConnection
from src.database.db_functions import get_sign_by_token, get_all_signs
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
                print(f"[DB_IO] Retrieved sign for token: {token}")
            else:
                # Word not in DB
                print(f"[DB_IO] Token '{token}' not found in database.")
                
                # log missing token to tokens_to_add.txt for later addition
                lines = open(NONEXIST_TOKENS_FILE).read().splitlines()
                lines.append(token)
                lines.sort()
                open(NONEXIST_TOKENS_FILE, "w").write("\n".join(lines))
                
                # finger spell the missing token
                for char in token:
                    sign_data = get_sign_by_token(char)
                    if sign_data:
                        file_io.push_motion_script(sign_data)
                        print(f"[DB_IO] Finger spelling character: {char}")
                    else:
                        print(f"[DB_IO] Character '{char}' not found in database for finger spelling.")
        
        
        # Reset event after processing all tokens
        file_io.asl_new_signal.clear()

        # Reduce thread load
        time.sleep(0.01)