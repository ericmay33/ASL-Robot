from src.text_to_ASL.translate_AI import translate_to_asl_gloss
import time

def run_ai(file_io):
    print("[AI_IO] Started AI translation loop.")

    while True:
        # Wait until STT signals that a new line is available
        file_io.stt_new_signal.wait()

        # Process all lines currently in the STT queue
        while not file_io.stt_line_queue.empty():
            line = file_io.pop_stt_line()
            print(f"[AI_IO] Received STT input: '{line}'")

            # Translate to ASL gloss tokens
            tokens = translate_to_asl_gloss(line)
            if not tokens:
                continue

            print(f"[AI_IO] Translated tokens: {tokens}")

            # Push each token individually to the ASL token queue
            for token in tokens:
                file_io.push_asl_token(token)
                print(f"[AI_IO] Queued ASL token: {token}")
        
        # Reduce thread load
        time.sleep(0.01)

    # Once STT queue is empty, the signal will be cleared by FileIOManager
    # and this loop will go back to waiting for the next STT signal