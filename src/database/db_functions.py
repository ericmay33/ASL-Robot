from src.database.db_connection import DatabaseConnection

# Return one sign document by token.
def get_sign_by_token(token: str):
    collection = DatabaseConnection.get_collection()
    return collection.find_one({"token": token.upper()})

# Insert new sign document into DB.
def insert_sign(sign_data: dict):
    collection = DatabaseConnection.get_collection()
    try:
        collection.insert_one(sign_data)
    except Exception as e:
        print(f"[DB] Insert failed: {e}")

# Delete one sign by token.
def delete_sign_by_token(token: str):
    collection = DatabaseConnection.get_collection()
    result = collection.delete_one({"token": token.upper()})
    return result.deleted_count

# Get all signs in the DB
def get_all_signs():
    collection = DatabaseConnection.get_collection()
    return list(collection.find({}))