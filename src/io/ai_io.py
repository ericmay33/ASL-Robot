import time

from src.text_to_ASL.translate_AI import translate_to_asl_gloss


def run_ai(file_io):
    print("[AI_IO] Started AI translation loop.")

    while not file_io.shutdown.is_set():
        if not file_io.stt_new_signal.wait(timeout=0.5):
            continue

        while not file_io.stt_line_queue.empty() and not file_io.shutdown.is_set():
            line = file_io.pop_stt_line()
            tokens = translate_to_asl_gloss(line)
            if not tokens:
                continue
            for token in tokens:
                file_io.push_asl_token(token)

        time.sleep(0.01)