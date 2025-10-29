from src.database.db_connection import get_database
from src.config.settings import SETTINGS

def test_db_connection():
    # Simple test to ensure MongoDB connection works.
    try:
        db = get_database()
        print("Connection success:", db.name)
        print("Collections:", db.list_collection_names())
    except Exception as e:
        print("Connection failed:", e)

if __name__ == "__main__":
    test_db_connection()