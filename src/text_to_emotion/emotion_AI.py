from pathlib import Path
from transformers import pipeline
from PIL import Image, ImageTk
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

root = None
label = None
screen_width = None
screen_height = None
current_image = None
previous_pil_image = None

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
        "ache", "achey", "aching", "hurt", "hurting", "pain", "painful",
        "injury", "injured", "sore", "soreness", "stabbing", "throbbing",
        "burn", "burning", "cramp", "cramping", "stiff", "tender", "wound",
        "bruise", "bruised", "cut", "cuts", "scrape", "sprain", "strained",
        "migraine", "headache", "nausea", "vomit", "fever", "ill", "weak",
        "exhausted", "fatigue", "dizzy", "dizziness"
    }

    for i in range(0, len(words), window_size):
        chunk_words = words[i:i + window_size]
        chunk = " ".join(chunk_words)

        if not chunk.strip():
            continue

        # Normalize to lowercase
        lower_chunk_words = {w.lower() for w in chunk_words}

        if lower_chunk_words & question_words:
            emotions.append("question")
            continue  # skip emotion classifier

        if lower_chunk_words & pain_words:
            emotions.append("pain")
            continue

        result = classifier(chunk)[0]

        if result["score"] >= CONFIDENCE_THRESHOLD:
            emotions.append(result["label"])
        else:
            emotions.append("neutral")

    return emotions

def show_emotion(emotions):
    if isinstance(emotions, str):
        emotions = [emotions]

    play_emotion_sequence(emotions)

def play_emotion_sequence(emotions, index=0):
    if index >= len(emotions):
        return  # Done

    emotion = emotions[index]

    image_path = BASE_DIR / "src" / "cache" / "emotions" / f"{emotion}.jpg"
    new_image = Image.open(image_path).resize((screen_width, screen_height))

    animate_transition(new_image, lambda: root.after(
        800,  # hold time before next emotion
        lambda: play_emotion_sequence(emotions, index + 1)
    ))

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
