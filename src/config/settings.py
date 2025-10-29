import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    # Central configuration class for the project, using .env variables

    # MongoDB
    MONGODB_URI: str = os.getenv("MONGODB_URI")
    MONGODB_DB_NAME: str = os.getenv("MONGODB_DB_NAME")
    GOOGLE_STT: dict = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

    SIGNS_COLLECTION: str = "signs"

    # Future examples:
    # MODEL_PATH: str = "models/asl_model.pth"
    # AUDIO_INPUT_DEVICE: int = 1


    def validate(self):
        # Check that all required environment variables are loaded
        missing = []
        if not self.MONGODB_URI:
            missing.append("MONGODB_URI")
        if not self.MONGODB_DB_NAME:
            missing.append("MONGODB_DB_NAME")
        if missing:
            raise ValueError(f"Missing environment variables: {', '.join(missing)}")

SETTINGS = Settings()
SETTINGS.validate()