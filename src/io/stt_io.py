from src.io.fileIO import FileIOManager
from src.speech_to_text.stt_factory import create_stt


def run_stt(file_io: FileIOManager):
    stt = create_stt()
    try:
        stt.start_stream()
        for line in stt.get_transcripts():
            file_io.push_stt_line(line)
    finally:
        stt.stop_stream()