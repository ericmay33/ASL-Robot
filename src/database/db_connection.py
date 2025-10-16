from src.config.settings import SETTINGS
from pymongo import MongoClient

def get_database():
    # Returns a db object that can be used for collection operations
    client = MongoClient(SETTINGS.MONGODB_URI)
    db = client[SETTINGS.MONGODB_DB_NAME]
    return db