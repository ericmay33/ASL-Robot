import pyaudio
from google.cloud import speech
from google.oauth2 import service_account

# Authentication 
client_file = 'stt_key_file.json' 
credentials = service_account.Credentials.from_service_account_file(client_file)
client = speech.SpeechClient(credentials=credentials)

# Audio setup 
RATE = 16000  # Sample rate (Hz)
CHUNK = int(RATE / 50)  # 50ms chunks

def mic_audio_stream():
    # Create an audio stream from the microphone
    p = pyaudio.PyAudio()
    stream = p.open(
        format=pyaudio.paInt16,
        channels=1,
        rate=RATE,
        input=True,
        frames_per_buffer=CHUNK,
    )

    try:
        while True:
            data = stream.read(CHUNK, exception_on_overflow=False)
            yield speech.StreamingRecognizeRequest(audio_content=data)
    except GeneratorExit:
        stream.stop_stream()
        stream.close()
        p.terminate()

def listen():
    # Streams from the microphone and yields final transcript lines.
    # Activation: listens for 'start moving' / 'stop moving' phrases.
    # Yields: str (final transcript text between activation and stop)
    config = speech.RecognitionConfig(
        encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
        sample_rate_hertz=RATE,
        language_code="en-US",
    )

    streaming_config = speech.StreamingRecognitionConfig(
        config=config,
        interim_results=True,
    )

    responses = client.streaming_recognize(streaming_config, mic_audio_stream())
    trans_begun = False

    for response in responses:
        for result in response.results:
            if not result.alternatives:
                continue

            transcript = result.alternatives[0].transcript.lower().strip()

            if result.is_final:
                if "start moving" in transcript and not trans_begun:
                    trans_begun = True
                    print("\nTransmission Begun")

                elif "stop moving" in transcript and trans_begun:
                    print("Transmission Ended. Exiting")
                    return  # gracefully end the generator

                elif trans_begun:
                    print("Final transcript:", transcript)
                    yield transcript