# Imports
import os
import time
import pandas as pd
import json
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from google import genai
from google.genai import types
from datetime import datetime, timedelta
from src.config.settings import SETTINGS

from src.database.db_connection import DatabaseConnection
from src.database.db_functions import get_sign_by_token


#Configs
client = genai.Client(api_key=SETTINGS.GEMINI_API_KEY)
model_name = "gemini-2.5-flash" 
output_filename = "gemini_output_log.txt"

WATCH_DIRECTORY = "InputFiles"
OUTPUT_DIRECTORY = "OutputFiles"
TARGET_FILE_NAME = "input.txt" 

#store tokens not in the database
def fetch_tokens(response):
    """
    Stores tokens not in the database
    """
    tokens = response.text.split()
    
    for token in tokens:
        # nonexist token log
        token_file = os.path.join(OUTPUT_DIRECTORY, "nonexist_tokens.txt")
        
        #translated token output
        output_filename = os.path.join(OUTPUT_DIRECTORY, "machineinstructions.txt")
        
        #test in DB
        exists = get_sign_by_token(token) #replace False with db access
        if exists is None:
            # write to file
            with open(token_file, 'a', encoding='utf-8') as outfile:
                outfile.write(f"\n{token}")
        else:
            with open(output_filename, 'a', encoding='utf-8') as outfile:
                outfile.write(f"\n{exists}")

#translation
def process_text_change(file_path):

    """
    Reads the text content of the modified file and processes it with Gemini.
    """

    print(f"-> Change detected in: {TARGET_FILE_NAME}. Processing...")

    try:
        # Read the LATEST content of the file
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read().strip() # .strip() removes leading/trailing whitespace

        if not content:
            print("!! File is empty after modification. Skipping AI call.")
            return

        system_instruction = f"You are an expert ASL translator who translates textual and spoken English input into ASL gloss. Do not include any extra commentary, headers, or surrounding text; only provide the translated text."

        prompt = f"Translate the following text into ASL gloss:\n\n---\n{content}\n---"

        # Call the Gemini API

        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config={
                "system_instruction": system_instruction
            }
        )

        # Save the Output to a Log
        output_filename = os.path.join(OUTPUT_DIRECTORY, "gemini_output_log.txt")

        # Open in append mode ('a') to keep a history of all changes
        with open(output_filename, 'w', encoding='utf-8') as outfile:
            outfile.write(f"{response.text}\n")
            fetch_tokens(response)

        print(f"<- Successfully processed and logged output to: {output_filename}")

       
    except Exception as e:
        print(f"!! An error occurred while processing {file_path}: {e}")


# change detection
class TextChangeHandler(FileSystemEventHandler):
    """
    Custom handler to process the modified file.
    """
    def __init__(self):
        self.last_modified = datetime.now()

    def on_modified(self, event):
        # We only care about file modification events (not directory changes)
        if not event.is_directory:
            file_path = event.src_path
            # CRITICAL: Only process the TARGET file
            if os.path.basename(file_path).lower() == TARGET_FILE_NAME.lower():

                # Introduce a small delay (0.5s) to ensure the file save operation is complete
                time.sleep(0.5)
                
                if datetime.now() - self.last_modified < timedelta(seconds =1):
                    process_text_change(file_path)
                    return
                else: 
                    self.last_modified = datetime.now()

# Main Execution Loop 
if __name__ == "__main__":
    
    DatabaseConnection.initialize()
    
    # 🚨 Initial check for the input file
    input_file_path = os.path.join(WATCH_DIRECTORY, TARGET_FILE_NAME)

    if not os.path.exists(input_file_path):
        print(f"!! WARNING: Input file '{TARGET_FILE_NAME}' not found in '{WATCH_DIRECTORY}'.")
        print("!! Please create the file to start monitoring.")

    event_handler = TextChangeHandler()
    observer = Observer()

    # Schedule the handler to monitor the directory non-recursively
    observer.schedule(event_handler, WATCH_DIRECTORY, recursive=False)

    # Start the observer thread
    observer.start()

    print(f"\n*** Watchdog is RUNNING ***")
    print(f"   Monitoring directory: {WATCH_DIRECTORY}")
    print(f"   Target file:          {TARGET_FILE_NAME}")

    try:
        # Keep the main thread alive until interrupted
        while True:
            time.sleep(10)

    except KeyboardInterrupt:
        observer.stop()
        print("\nWatchdog stopped by user (Ctrl+C).")

    observer.join()