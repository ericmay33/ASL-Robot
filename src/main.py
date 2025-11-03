from src.database.db_connection import DatabaseConnection
from src.database.db_functions import get_sign_by_token

DatabaseConnection.initialize()

signs = ["HELLO", "NO", "I"]

for sign in signs:
    sign_data = get_sign_by_token(sign)
    print(f"Retrieved sign: {sign_data}")