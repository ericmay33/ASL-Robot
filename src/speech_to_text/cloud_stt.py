"""Cloud STT - thin wrapper around existing stt.listen(). No logic changes."""

from typing import Generator

from src.speech_to_text.base_stt import BaseSTT
from src.speech_to_text.stt import listen


class CloudSTT(BaseSTT):
    """Minimal wrapper around existing listen() generator. Stream lifecycle is handled internally."""

    def start_stream(self) -> None:
        """No-op - listen() handles stream setup internally."""
        pass

    def stop_stream(self) -> None:
        """No-op - listen() handles cleanup on generator exit."""
        pass

    def get_transcripts(self) -> Generator[str, None, None]:
        """Yield from existing listen() generator."""
        yield from listen()

    def is_ready(self) -> bool:
        """Cloud STT is ready when instantiated."""
        return True

    @property
    def engine_name(self) -> str:
        return "cloud"
