from threading import Thread
from src.io.fileIO import FileIOManager
from src.io.stt_io import run_stt
from src.io.ai_io import run_ai

if __name__ == "__main__":
    file_io = FileIOManager()

    stt_thread = Thread(target=run_stt, args=(file_io,), daemon=True)
    ai_thread = Thread(target=run_ai, args=(file_io,), daemon=True)

    stt_thread.start()
    ai_thread.start()

    print("[MAIN] System initialized. Listening for speech...")

    stt_thread.join()
    ai_thread.join()