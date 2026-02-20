from src.text_to_emotion.emotion_AI import translate_to_emotion

def run_emotion(file_io, emotion_gui_queue):
    print("[EMOTION_IO] Started emotion processing loop.")

    while True:
        file_io.stt_emotion_signal.wait()

        while not file_io.stt_emotion_queue.empty():
            line = file_io.pop_stt_emotion_line()
            print(f"[EMOTION_IO] Received: {line}")

            emotion = translate_to_emotion(line)

            # Send emotion to GUI queue
            emotion_gui_queue.put(emotion)
