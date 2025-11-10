import json
from pymongo import MongoClient
from src.config.settings import SETTINGS
from src.database.db_connection import DatabaseConnection

def seed_signs(reset=False):
    DatabaseConnection.initialize()
    collection = DatabaseConnection.get_collection()

    with open("src/signs/signs_to_seed.json", "r") as f:
        signs = json.load(f)

    if reset:
        print("[SEED] Reset mode enabled. Dropping all existing signs...")
        collection.delete_many({})

    existing = {doc["token"]: doc for doc in collection.find({}, {"_id": 0})}

    for sign in signs:
        token = sign["token"].upper()
        if token not in existing:
            print(f"[SEED] Inserting new token: {token}")
            collection.insert_one(sign)
        elif existing[token] != sign:
            print(f"[SEED] Updating changed token: {token}")
            collection.replace_one({"token": token}, sign)

    # Remove tokens that exist in DB but not in file
    json_tokens = {s["token"].upper() for s in signs}
    for token in existing.keys():
        if token not in json_tokens:
            print(f"[SEED] Removing token: {token} from database.")
            collection.delete_one({"token": token})

    print("[SEED] Database synchronized successfully.")

if __name__ == "__main__":
    seed_signs(reset=False)
