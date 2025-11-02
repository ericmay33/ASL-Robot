from pymongo import MongoClient
from src.config.settings import SETTINGS

class DatabaseConnection:
    client = None
    db = None
    signs = None

    # Initialize one MongoDB connection.
    @classmethod
    def initialize(cls):
        if cls.client is None:
            cls.client = MongoClient(SETTINGS.MONGODB_URI)
            cls.db = cls.client[SETTINGS.MONGODB_DB_NAME]
            cls.signs = cls.db["signs"]
            cls.signs.create_index("token", unique=True)
            print("[DB] Connected and token index created.")

    # Return the 'signs' collection.
    @classmethod
    def get_collection(cls):
        if cls._signs is None:
            raise Exception("Database not initialized.")
        return cls.signs