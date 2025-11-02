from src.database.db_connection import DatabaseConnection
from src.database.db_functions import get_sign_by_token

def main():
    # Initialize the database connection once at startup.
    DatabaseConnection.initialize()

    # Example usage: database function call after initialization.
    sign = get_sign_by_token("HELLO")
    if sign:
        print(sign)

if __name__ == "__main__":
    main()