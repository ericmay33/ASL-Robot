import time

from src.text_to_ASL.translate_AI import translate_to_asl_gloss
from src.text_to_emotion.emotion_AI import translate_to_emotions


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
            emotions = translate_to_emotions(line)
            if not emotions:
                emotions = ["neutral"]
            token_count = len(tokens)
            emotion_count = len(emotions)

            for idx, token in enumerate(tokens):
                # Map gloss tokens across chunk-level emotions from the source text.
                # This preserves multi-chunk emotion variation while syncing to motion start.
                emotion_idx = min(emotion_count - 1, (idx * emotion_count) // token_count)
                motion_emotion = emotions[emotion_idx]
                file_io.push_asl_token(token)
                file_io.push_motion_emotion(motion_emotion)

        time.sleep(0.01)