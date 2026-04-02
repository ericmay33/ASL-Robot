import time

from src.database.db_connection import DatabaseConnection
from src.io.sign_resolution import enqueue_motions_for_token


def run_database(file_io):
    DatabaseConnection.initialize()
    print("[DB_IO] Started database I/O handler loop.")

    while not file_io.shutdown.is_set():
        # Wait for tokens from AI_IO (timeout to check shutdown)
        if not file_io.asl_new_signal.wait(timeout=0.5):
            continue

        # Process all tokens in the queue
        while not file_io.asl_token_queue.empty() and not file_io.shutdown.is_set():
            token = file_io.pop_asl_token()
            enqueue_motions_for_token(file_io, token, log=True, log_tag="[DB_IO]")

        # Reset event after processing all tokens
        file_io.asl_new_signal.clear()

        # Reduce thread load
        time.sleep(0.01)