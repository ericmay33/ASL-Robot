import io
import os
import sys
import pyaudio
from google.cloud import speech
from google.oauth2 import service_account
from dotenv import load_dotenv

# Authentication 
client_file = 'stt_key_file.json' 
credentials = service_account.Credentials.from_service_account_file(client_file)
client = speech.SpeechClient(credentials=credentials)
OUTPUT_DIRECTORY = r"C:\Users\Morgan\Downloads\fall_25\Capstone1\ASL-Robot\InputFiles"

# Audio setup 
RATE = 16000  # Sample rate (Hz)
CHUNK = int(RATE / 50)  # 50ms chunks

# Create an audio stream from the microphone
p = pyaudio.PyAudio()
stream = p.open(
    format=pyaudio.paInt16,
    channels=1,
    rate=RATE,
    input=True,
    frames_per_buffer=CHUNK,
)

def generator():
    """Yields audio chunks from the microphone."""
    while True:
        data = stream.read(CHUNK, exception_on_overflow=False)
        yield speech.StreamingRecognizeRequest(audio_content=data)

# Config 
config = speech.RecognitionConfig(
    encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
    sample_rate_hertz=RATE,
    language_code="en-US",
)

streaming_config = speech.StreamingRecognitionConfig(
    config=config,
    interim_results=True,   # get partial results while speaking
)

# Assign the iterator directly to a variable
responses = client.streaming_recognize(streaming_config, generator())

trans_begun = False

token_file = os.path.join(OUTPUT_DIRECTORY, "input.txt")

# work after a prompt
for response in responses:
    for result in response.results:
        # Check if any alternatives to process 
        if not result.alternatives:
            continue

        transcript = result.alternatives[0].transcript.lower().strip()

        if result.is_final:
            
            if "start moving" in transcript and not trans_begun:
                # Phrase was detected, start the transmission.
                trans_begun = True
                print("\nTransmission Begun")
                # Now it's final and it's been activated, print so it doesn't print before activation
                print("Final transcript:", transcript) 
            
            elif "stop moving" in transcript and trans_begun:
                # Phrase was detected, print it, and then terminate.
                print("Final transcript:", transcript)
                print("Transmission Ended. Exiting")
                sys.exit()
            
            elif trans_begun:
                # handles all final results between the start and end phrases
                print("Final transcript:", transcript)
                with open(token_file, 'a', encoding='utf-8') as outfile:
                    outfile.write(transcript + "\n")

        #else: # interim results
        #    if trans_begun:
        #        # Handles all interim results between the start and end phrases
        #        print("Interim:", transcript, end="\r")