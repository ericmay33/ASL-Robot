import sys
from threading import Thread
from src.io.fileIO import FileIOManager
from src.io.stt_io import run_stt
from src.io.ai_io import run_ai
from src.io.db_io import run_database
from src.io.motion_io import run_motion

JOIN_TIMEOUT = 1.0
JOIN_MAX_WAIT = 5.0

if __name__ == "__main__":
    file_io = FileIOManager()

    stt_thread = Thread(target=run_stt, args=(file_io,), daemon=True)
    ai_thread = Thread(target=run_ai, args=(file_io,), daemon=True)
    db_thread = Thread(target=run_database, args=(file_io,), daemon=True)
    motion_thread = Thread(target=run_motion, args=(file_io,), daemon=True)

    stt_thread.start()
    ai_thread.start()
    db_thread.start()
    motion_thread.start()

    print("[MAIN] System initialized. Listening for speech... (Ctrl+C to exit)")

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
