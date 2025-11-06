from src.io.fileIO import FileIOManager
from src.speech_to_text.stt import listen
import time

def run_stt(file_io: FileIOManager):
    for line in listen():
        file_io.push_stt_line(line)