import sys
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
JOIN_TIMEOUT = 1.0
JOIN_MAX_WAIT = 5.0

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

    print("[MAIN] System initialized. Listening for speech... (Ctrl+C to exit)")

    # gui polling
    def poll_emotion_queue():
        while not emotion_gui_queue.empty():
            emotion = emotion_gui_queue.get()
            show_emotion(emotion)

        root.after(50, poll_emotion_queue)  # check again in 50ms

    poll_emotion_queue()

    # Tkinter event loop MUST stay in main thread
    root.mainloop()
    try:
        threads = [stt_thread, ai_thread, db_thread, motion_thread]
        while any(t.is_alive() for t in threads):
            for t in threads:
                t.join(timeout=JOIN_TIMEOUT)
    except KeyboardInterrupt:
        print("\n[MAIN] Shutting down...")
        file_io.shutdown.set()
        waited = 0.0
        while waited < JOIN_MAX_WAIT and any(t.is_alive() for t in [stt_thread, ai_thread, db_thread, motion_thread]):
            for t in [stt_thread, ai_thread, db_thread, motion_thread]:
                t.join(timeout=JOIN_TIMEOUT)
            waited += JOIN_TIMEOUT
        if any(t.is_alive() for t in [stt_thread, ai_thread, db_thread, motion_thread]):
            print("[MAIN] Some threads did not exit in time (daemon threads will be cleaned up).")
        print("[MAIN] Goodbye.")
        sys.exit(0)
