"""Quick test for STT engines. Usage: python -m src.testing.test_stt local|cloud"""

import os
import sys

# Set STT_ENGINE before any imports that load settings
if len(sys.argv) < 2:
    print("Usage: python -m src.testing.test_stt cloud|local")
    sys.exit(1)
engine = sys.argv[1].lower()
if engine not in ("cloud", "local"):
    print("Engine must be 'cloud' or 'local'")
    sys.exit(1)
os.environ["STT_ENGINE"] = engine

from src.speech_to_text.stt_factory import create_stt


def main():
    stt = create_stt()
    print(f"Testing {stt.engine_name} STT engine. Say wake word, then speak. First 10 transcripts:\n")

    count = 0
    try:
        stt.start_stream()
        for transcript in stt.get_transcripts():
            print(f"  [{count + 1}] {transcript}")
            count += 1
            if count >= 10:
                print("\nReached 10 transcripts. Stopping.")
                break
    finally:
        stt.stop_stream()

    print(f"\nDone. Received {count} transcript(s).")


if __name__ == "__main__":
    main()
