# SeniorProjectASLRobot

## 📁 Project Structure

```
Main-Folder/
│
├── src/
│   ├── main.py                         # Entry point for running the system
│   ├── config/
│   │   └── settings.py                 # Loads environment variables
│   ├── database/
│   │   ├── db_connection.py            # MongoDB connection utility
│   │   ├── create_signs_collection.py
│   │   └── test_db_connection.py
│   └── ...
├──
├── .gitignore
├── .env                                # Stores credentials (not tracked in Git)
├── requirements.txt                    # Python dependencies
└── README.md                           # Project overview and setup instructions
```

---

## ⚙️ 1. Installing Dependencies

Ensure Python 3.10+ is installed. Then, from the project root directory:

```bash
pip install -r requirements.txt
```

This will install:

* `pymongo` (MongoDB client)
* `python-dotenv` (environment variable loader)
* ...

---

## 🔐 2. .env File Setup

Create a `.env` file in the project root directory with the following:

```
MONGO_URI=mongodb+srv://<USERNAME>:<PASSWORD>@<YOUR_CLUSTER>.mongodb.net/
MONGO_DB_NAME=ASLSignsDB
```

> **Note:** Replace `<USERNAME>` and `<PASSWORD>` with the project’s MongoDB superuser credentials.

This .env file should remain private and not tracked by Git. Credentials can be found in shared OneDrive folder.


## 🏃 3. Running the Project

Once setup is complete, you can run the project with the following command:

```bash
python -m src.main
```

---