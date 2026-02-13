"""Abstract base class for STT engines. Both cloud and local implementations share this interface."""

from abc import ABC, abstractmethod
from typing import Generator


class BaseSTT(ABC):
    """Interface that both Cloud STT and Local STT must implement."""

    @abstractmethod
    def start_stream(self) -> None:
        """Initialize audio stream. May be no-op for engines that handle this internally."""
        pass

    @abstractmethod
    def stop_stream(self) -> None:
        """Clean up resources. May be no-op for engines that handle this internally."""
        pass

    @abstractmethod
    def get_transcripts(self) -> Generator[str, None, None]:
        """Yield transcript strings. Same format for both engines."""
        yield  # Make this a generator; subclasses will yield actual transcripts

    @abstractmethod
    def is_ready(self) -> bool:
        """Check if engine is ready to transcribe."""
        pass

    @property
    @abstractmethod
    def engine_name(self) -> str:
        """Engine name for logging."""
        pass
