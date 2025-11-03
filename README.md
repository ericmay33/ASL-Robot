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
│   │   ├── db_connection.py            # MongoDB connection initlization
│   │   └── db_functions.py             # MongoDB database function/interaction
│   └── speech_to_text/
│       └── stt.py                      # Speech to text
│   └── text_to_ASL/
│       └── translate_AI.py             # AI text to ASL 
│  
├── translator.ipynb                    # AI text to ASL Translation
├── stt_key_file.json                   # Stores credentials (not tracked in Git)
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
* `python-dotenv` (.env variable loader)
* `google-cloud-speech`
* `google-auth`
* `pyaudio`
* `google-genai`
* `watchdog`
* `pandas`


---

## 🔐 2. .env File Setup

Create a `.env` file in the project root directory with the following:

```
MONGO_URI=mongodb+srv://<USERNAME>:<PASSWORD>@<YOUR_CLUSTER>.mongodb.net/
MONGO_DB_NAME=ASLSignsDB

GOOGLE_APPLICATION_CREDENTIALS="stt_key_file.json"

GEMINI_API_KEY="apikey"
```

> **Note:** Replace `<USERNAME>` and `<PASSWORD>` with the project’s MongoDB superuser credentials.


This .env file should remain private and not tracked by Git. Credentials can be found in shared OneDrive folder.

---

## 🔑 3. Speech-to-Text (STT) Credentials Setup

The Speech-to-Text module uses a **JSON key file** for secure authentication with the Google Cloud Speech-to-Text API. This file contains sensitive service account credentials and must be set up correctly.

### A. Obtain and Name the Key File

1. Locate the necessary Google Cloud Service Account JSON file (which contains the required credentials).
2. **Save this file** in the **root** of your project directory.
3. You **must** rename the file exactly as referenced in your `.env` file: `stt_key_file.json`.

### B. Authentication Process

* The environment variable **`GOOGLE_APPLICATION_CREDENTIALS`** tells the `google-auth` library where to find the key file.
* The `stt.py` module uses this path to securely authenticate to the Google API, ensuring credentials are not **hardcoded** into the application.

### C. Security Best Practice

* Verify that both **`stt_key_file.json`** and **`.env`** are explicitly listed in your `.gitignore` file to prevent sharing.

---

## 🏃 4. Running the Project

Once setup is complete, you can run the project with the following command:

```bash
python -B -m src.main
```

---