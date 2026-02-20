
from src.database.db_connection import DatabaseConnection
from src.database.db_functions import get_all_signs

DatabaseConnection.initialize()

all_signs = get_all_signs()
for sign in all_signs:
    # print(f" {sign.get('token')}")
    print(sign)