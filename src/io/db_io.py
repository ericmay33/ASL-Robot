from src.database.db_connection import DatabaseConnection
from src.database.db_functions import get_sign_by_token
import time

# will fill with motion scripts for letters when hardware for hand supports signs
FINGERSPELL_CACHE = {
    "A": None,
    "B": None,
    "C": None,
    "D": None,
    "E": None,
    "F": None,
    "G": None,
    "H": None,
    "I": None,
    "J": None,
    "K": None,
    "L": None,
    "M": None,
    "N": None,
    "O": None,
    "P": None,
    "Q": None,
    "R": None,
    "S": None,
    "T": None,
    "U": None,
    "V": None,
    "W": None,
    "X": None,
    "Y": None,
    "Z": None,
}

def run_database(file_io):
    DatabaseConnection.initialize()
    print("[DB_IO] Started database I/O handler loop.")

    while True:
        # Wait for tokens from AI_IO
        file_io.asl_new_signal.wait()
        
        # Process all tokens in the queue
        while not file_io.asl_token_queue.empty():
            token = file_io.pop_asl_token()

            # Try to retreive sign data from database
            sign_data = get_sign_by_token(token)

            if sign_data:
                file_io.push_motion_script(sign_data)
                print(f"[DB_IO] Retrieved sign for token: {token}")
                continue

            # FALLBACK -> Fingerspelling
            print(f"[DB_IO] Token '{token}' not in DB. Falling back to fingerspelling.")

            for letter in token:
                if not letter.isalpha():
                    continue

                letter = letter.upper()

                # Check if the letter exists in cache
                letter_sign = FINGERSPELL_CACHE.get(letter)

                if letter_sign:
                    file_io.push_motion_script(letter_sign)
                    print(f"[DB_IO] Added fingerspelling letter: {letter}")
                else:
                    print(f"[DB_IO] WARNING: No fingerspelling JSON for '{letter}'")

        # Reset event after processing all tokens
        file_io.asl_new_signal.clear()

        # Reduce thread load
        time.sleep(0.01)