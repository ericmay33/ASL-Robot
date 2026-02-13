"""Factory for creating STT engine based on STT_ENGINE env variable."""

import os
from typing import TYPE_CHECKING

from src.speech_to_text.base_stt import BaseSTT

if TYPE_CHECKING:
    from src.speech_to_text.cloud_stt import CloudSTT
    from src.speech_to_text.local_stt import LocalSTT


def create_stt() -> BaseSTT:
    """
    Create STT engine based on STT_ENGINE environment variable.
    - STT_ENGINE=cloud -> CloudSTT (Google Cloud Speech)
    - STT_ENGINE=local -> LocalSTT (Whisper)
    """
    engine = os.getenv("STT_ENGINE", "cloud").lower().strip()

    if engine == "cloud":
        from src.speech_to_text.cloud_stt import CloudSTT
        return CloudSTT()
    elif engine == "local":
        from src.speech_to_text.local_stt import LocalSTT
        model = os.getenv("LOCAL_STT_MODEL", "base")
        device = os.getenv("LOCAL_STT_DEVICE", "cpu")
        return LocalSTT(model_name=model, device=device)
    else:
        raise ValueError(
            f"Invalid STT_ENGINE='{engine}'. Must be 'cloud' or 'local'. "
            "Set STT_ENGINE in .env file."
        )
