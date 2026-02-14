from queue import Queue
from threading import Event


class FileIOManager:
    def __init__(self):
        self.stt_line_queue = Queue()
        self.asl_token_queue = Queue()
        self.motion_queue = Queue()
        self.stt_new_signal = Event()
        self.asl_new_signal = Event()
        self.motion_new_signal = Event()
        self.shutdown = Event()
        
    def push_stt_line(self, line):
        self.stt_line_queue.put(line)
        self.stt_new_signal.set()

    def pop_stt_line(self):
        line = self.stt_line_queue.get()
        if self.stt_line_queue.empty():
            self.stt_new_signal.clear()
        return line
    
    def push_asl_token(self, token):
        self.asl_token_queue.put(token)
        self.asl_new_signal.set()
    
    def pop_asl_token(self):
        token = self.asl_token_queue.get()
        if self.asl_token_queue.empty():
            self.asl_new_signal.clear()
        return token
    
    def push_motion_script(self, motion_script):
        self.motion_queue.put(motion_script)
        self.motion_new_signal.set()

    def pop_motion_script(self):
        motion_script = self.motion_queue.get()
        if self.motion_queue.empty():
            self.motion_new_signal.clear()
        return motion_script