from pathlib import Path
from collections import deque
import string
from transformers import pipeline
from PIL import Image, ImageTk, ImageOps
import tkinter as tk
import os
from dotenv import load_dotenv
from huggingface_hub import login

load_dotenv()
hf_token = os.getenv("EVAN_HUGGING_FACE_LOGIN")
login(hf_token)

classifier = pipeline(
    "text-classification",
    model="j-hartmann/emotion-english-distilroberta-base",
    return_all_scores=True,
    local_files_only=True
)

BASE_DIR = Path(__file__).resolve().parent.parent.parent
CONFIDENCE_THRESHOLD = 0.70
DISPLAY_ROTATION_DEGREES = 90
BACKGROUND_COLOR = (255, 255, 255)

root = None
label = None
screen_width = None
screen_height = None
current_image = None
previous_pil_image = None
pending_emotions = deque()
is_playing = False

# creates a persistent window that is the size of the screen
def make_window():
    global root, label, screen_width, screen_height

    root = tk.Tk()
    root.title("ASL Robot Emotion Display")

    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()

    root.geometry(f"{screen_width}x{screen_height}")

    label = tk.Label(root)
    label.pack(fill="both", expand=True)

    root.update_idletasks()  # Ensure window is ready

    # Show neutral first
    show_emotion("neutral")

    return root

# uses the hugging face model to get the emotion attached to the sentence
def translate_to_emotions(text: str, window_size: int = 10) -> list[str]:
    words = text.split()
    emotions = []

    question_words = {"who", "what", "when", "where", "why", "how"}
    pain_words = {
        "ache", "aches", "achey", "aching", "hurt", "hurts", "hurting", "pain", "painful",
        "injury", "injuried","injured", "sore", "soreness", "stabbing", "stabbings", "throbbing",
        "burn", "burning", "cramp", "cramps","cramping", "stiff", "stiffness", "tender", "tenderness", "wound", "wounds",
        "bruise", "bruises", "bruised", "cut", "cuts", "scrape", "scrapes", "scraping", "sprain", "strains", "strained",
        "migraine", "headache", "nausea", "vomit", "fever", "ill", "weak",
        "exhausted", "fatigue", "dizzy", "dizziness"
    }

    teeth_words = {
        "tooth", "teeth", "toothache", "brush",
        # emphasis / intensifier words (use teeth face for emphasis)
        "really", "very", "so", "too", "super", "extremely", "incredibly",
        "totally", "absolutely", "definitely", "seriously", "literally",
        "deeply", "strongly", "quite", "especially", "utterly", "completely",
    }

    for i in range(0, len(words), window_size):
        chunk_words = words[i:i + window_size]
        chunk = " ".join(chunk_words)

        if not chunk.strip():
            continue

        # Normalize to lowercase and strip punctuation for reliable keyword matching.
        lower_chunk_words = {w.lower().strip(string.punctuation) for w in chunk_words if w.strip(string.punctuation)}

        if lower_chunk_words & question_words:
            emotions.append("question")
            continue  # skip emotion classifier

        if lower_chunk_words & pain_words:
            emotions.append("pain")
            continue

        if lower_chunk_words & teeth_words:
            emotions.append("teeth")
            continue

        result = classifier(chunk)[0]

        if result["score"] >= CONFIDENCE_THRESHOLD:
            emotions.append(result["label"])
        else:
            emotions.append("neutral")

    return emotions

def show_emotion(emotions):
    global is_playing

    if isinstance(emotions, str):
        emotions = [emotions]

    for emotion in emotions:
        pending_emotions.append(emotion)

    if not is_playing:
        is_playing = True
        play_emotion_sequence([pending_emotions.popleft()], on_complete=_play_next_pending_emotion)

def _play_next_pending_emotion():
    global is_playing
    if pending_emotions:
        play_emotion_sequence([pending_emotions.popleft()], on_complete=_play_next_pending_emotion)
    else:
        is_playing = False

def play_emotion_sequence(emotions, index=0, on_complete=None):
    if index >= len(emotions):
        if on_complete:
            on_complete()
        return  # Done

    emotion = emotions[index]

    image_path = BASE_DIR / "src" / "cache" / "emotions" / f"{emotion}.png"
    new_image = prepare_image_for_screen(image_path)

    animate_transition(new_image, lambda: root.after(
        800,  # hold time before next emotion
        lambda: play_emotion_sequence(emotions, index + 1, on_complete=on_complete)
    ))

def prepare_image_for_screen(image_path):
    image = Image.open(image_path).convert("RGB")

    if DISPLAY_ROTATION_DEGREES % 360 != 0:
        image = image.rotate(DISPLAY_ROTATION_DEGREES, expand=True)

    # Preserve proportions by fitting inside the screen and letterboxing.
    fitted = ImageOps.contain(image, (screen_width, screen_height), Image.Resampling.LANCZOS)
    output = Image.new("RGB", (screen_width, screen_height), BACKGROUND_COLOR)
    paste_x = (screen_width - fitted.width) // 2
    paste_y = (screen_height - fitted.height) // 2
    output.paste(fitted, (paste_x, paste_y))
    return output

def animate_transition(new_image, on_complete=None):
    global current_image, previous_pil_image

    if previous_pil_image is None:
        previous_pil_image = new_image
        current_image = ImageTk.PhotoImage(new_image)
        label.config(image=current_image)
        if on_complete:
            on_complete()
        return

    steps = 10
    duration = 200
    delay = duration // steps

    def fade(step=0):
        global current_image, previous_pil_image

        if step > steps:
            previous_pil_image = new_image
            if on_complete:
                on_complete()
            return

        alpha = step / steps
        blended = Image.blend(previous_pil_image, new_image, alpha)

        current_image = ImageTk.PhotoImage(blended)
        label.config(image=current_image)

        root.after(delay, lambda: fade(step + 1))

    fade()
