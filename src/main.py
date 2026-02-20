from threading import Thread
from queue import Queue
import tkinter as tk

from src.io.fileIO import FileIOManager
from src.io.stt_io import run_stt
from src.io.ai_io import run_ai
from src.io.emotion_io import run_emotion
from src.io.db_io import run_database
from src.io.motion_io import run_motion

from src.text_to_emotion.emotion_AI import make_window, show_emotion

if __name__ == "__main__":
    file_io = FileIOManager()

    # Queue specifically for GUI updates
    emotion_gui_queue = Queue()

    # Create Tkinter window in MAIN THREAD
    root = make_window()

    # Start worker threads
    stt_thread = Thread(target=run_stt, args=(file_io,), daemon=True)
    ai_thread = Thread(target=run_ai, args=(file_io,), daemon=True)
    emotion_thread = Thread(target=run_emotion, args=(file_io, emotion_gui_queue), daemon=True)
    db_thread = Thread(target=run_database, args=(file_io,), daemon=True)
    motion_thread = Thread(target=run_motion, args=(file_io,), daemon=True)
    
    stt_thread.start()
    ai_thread.start()
    emotion_thread.start()
    db_thread.start()
    motion_thread.start()

    print("[MAIN] System initialized. Listening for speech...")

    # gui polling
    def poll_emotion_queue():
        while not emotion_gui_queue.empty():
            emotion = emotion_gui_queue.get()
            show_emotion(emotion)

        root.after(50, poll_emotion_queue)  # check again in 50ms

    poll_emotion_queue()

    # Tkinter event loop MUST stay in main thread
    root.mainloop()