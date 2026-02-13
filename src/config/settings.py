import os
import json
from dotenv import load_dotenv
from typing import Optional, Dict, Any

SETTINGS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(SETTINGS_DIR, '..', '..'))

load_dotenv()

creds_path_env: Optional[str] = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
GOOGLE_CREDS_PATH: Optional[str] = None
GOOGLE_CREDENTIALS: Optional[Dict[str, Any]] = None 

if creds_path_env:
    GOOGLE_CREDS_PATH = os.path.join(ROOT_DIR, creds_path_env)
    os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = GOOGLE_CREDS_PATH
    
    if os.path.exists(GOOGLE_CREDS_PATH):
        try:
            with open(GOOGLE_CREDS_PATH, 'r') as f:
                GOOGLE_CREDENTIALS = json.load(f)
        except json.JSONDecodeError:
            print(f"Error decoding JSON file at {GOOGLE_CREDS_PATH}")

class Settings:
    MONGODB_URI: Optional[str] = os.getenv("MONGODB_URI")
    MONGODB_DB_NAME: Optional[str] = os.getenv("MONGODB_DB_NAME")
    
    GOOGLE_CREDS_PATH: Optional[str] = GOOGLE_CREDS_PATH
    GOOGLE_CREDENTIALS: Optional[Dict[str, Any]] = GOOGLE_CREDENTIALS
    
    GEMINI_API_KEY: Optional[str] = os.getenv("GEMINI_API_KEY")
    
    SIGNS_COLLECTION: str = "signs"

    def validate(self):
        missing = []
        stt_engine = os.getenv("STT_ENGINE", "cloud").lower().strip()

        if not self.MONGODB_URI:
            missing.append("MONGODB_URI")
        if not self.MONGODB_DB_NAME:
            missing.append("MONGODB_DB_NAME")

        if stt_engine == "cloud":
            if not self.GOOGLE_CREDS_PATH:
                missing.append("GOOGLE_APPLICATION_CREDENTIALS (Path not set)")
            elif not os.path.exists(self.GOOGLE_CREDS_PATH):
                print(f"Warning: Google Credentials file not found at {self.GOOGLE_CREDS_PATH}")
                missing.append("Google Credentials file not found.")
            elif not self.GOOGLE_CREDENTIALS:
                missing.append("Google Credentials file could not be parsed as JSON.")

        if not self.GEMINI_API_KEY:
            missing.append("GEMINI_API_KEY")

        if missing:
            raise ValueError(f"Missing environment variables/invalid configuration: {', '.join(missing)}")

SETTINGS = Settings()
SETTINGS.validate()