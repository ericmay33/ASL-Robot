"""Local STT using OpenAI Whisper. Runs fully offline after model download."""

import os
import queue
import threading
from typing import Generator

import numpy as np
import pyaudio
import whisper

from src.speech_to_text.base_stt import BaseSTT

# Audio config - matches cloud STT
RATE = 16000
CHANNELS = 1
FORMAT = pyaudio.paInt16
CHUNK_DURATION = 3.0  # seconds
CHUNK_SIZE = int(RATE * CHUNK_DURATION * 2)  # 2 bytes per sample for int16

# Wake/stop phrases - same as cloud
WAKE_PHRASES = ["fred", "frederick", "freddy", "freddie", "hey fred", "fred please translate"]
STOP_PHRASES = ["stop moving", "fred stop", "thank you fred"]


class LocalSTT(BaseSTT):
    """Whisper-based local STT. Processes 3-second audio chunks in background thread."""

    def __init__(self, model_name: str = "base", device: str = "cpu"):
        self.model_name = model_name
        self.device = device
        self._model = None
        self._transcript_queue: queue.Queue[str | None] = queue.Queue()
        self._stop_event = threading.Event()
        self._worker_thread: threading.Thread | None = None
        self._audio_stream = None
        self._pyaudio: pyaudio.PyAudio | None = None

    def start_stream(self) -> None:
        """Load Whisper model. Audio capture starts when get_transcripts() runs."""
        if self._model is None:
            self._model = whisper.load_model(self.model_name, device=self.device)

    def stop_stream(self) -> None:
        """Signal worker to stop and clean up resources."""
        self._stop_event.set()
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=2.0)
        if self._audio_stream:
            try:
                self._audio_stream.stop_stream()
                self._audio_stream.close()
            except Exception:
                pass
            self._audio_stream = None
        if self._pyaudio:
            try:
                self._pyaudio.terminate()
            except Exception:
                pass
            self._pyaudio = None

    def _capture_and_transcribe(self) -> None:
        """Background thread: capture audio chunks, run Whisper, put transcripts in queue."""
        self._pyaudio = pyaudio.PyAudio()
        self._audio_stream = self._pyaudio.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=RATE,
            input=True,
            frames_per_buffer=1024,
        )

        buffer = b""
        try:
            while not self._stop_event.is_set():
                try:
                    data = self._audio_stream.read(1024, exception_on_overflow=False)
                    buffer += data

                    if len(buffer) >= CHUNK_SIZE:
                        chunk = buffer[:CHUNK_SIZE]
                        buffer = buffer[CHUNK_SIZE:]

                        # Normalize int16 to float32 [-1, 1]
                        audio_int16 = np.frombuffer(chunk, dtype=np.int16)
                        audio_float = audio_int16.astype(np.float32) / 32768.0

                        result = self._model.transcribe(
                            audio_float,
                            language="en",
                            fp16=(self.device == "cuda"),
                        )
                        text = result["text"].strip().lower()
                        if text:
                            self._transcript_queue.put(text)
                except Exception as e:
                    if not self._stop_event.is_set():
                        self._transcript_queue.put(None)  # Sentinel for error
                    break
        finally:
            self._transcript_queue.put(None)  # Sentinel for end of stream

    def get_transcripts(self) -> Generator[str, None, None]:
        """Yield transcripts with same wake/stop logic as cloud STT."""
        self.start_stream()
        self._stop_event.clear()
        self._transcript_queue = queue.Queue()
        self._worker_thread = threading.Thread(target=self._capture_and_transcribe)
        self._worker_thread.start()

        trans_begun = False
        try:
            while True:
                try:
                    transcript = self._transcript_queue.get(timeout=0.5)
                except queue.Empty:
                    continue

                if transcript is None:
                    break

                # Wake detection
                if any(phrase in transcript for phrase in WAKE_PHRASES) and not trans_begun:
                    trans_begun = True
                    print(f"\n[FRED] Activated! Listening for speech...\n")

                # Stop detection
                elif any(phrase in transcript for phrase in STOP_PHRASES) and trans_begun:
                    print("[FRED] Stopping translation. Goodbye!")
                    break

                # Regular speech while active
                elif trans_begun:
                    print(f"[FRED heard]: {transcript}")
                    yield transcript
        finally:
            self.stop_stream()

    def is_ready(self) -> bool:
        """Ready once model is loaded."""
        return self._model is not None

    @property
    def engine_name(self) -> str:
        return "local"
