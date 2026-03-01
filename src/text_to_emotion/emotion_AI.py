from pathlib import Path
from transformers import pipeline
from PIL import Image, ImageTk
import tkinter as tk

classifier = pipeline(
    "text-classification",
    model="j-hartmann/emotion-english-distilroberta-base",
    return_all_scores=True
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
def translate_to_emotion(text: str) -> str:
    results = classifier(text)
    top = max(results, key=lambda x: x["score"])

    if top["score"] < CONFIDENCE_THRESHOLD:
        return "neutral"

    return top["label"]

# takes the emotion received earlier and puts the png with the same name into the persistent window
def show_emotion(emotion: str):
    global current_image, previous_pil_image

    image_path = BASE_DIR / "src" / "cache" / "emotions" / f"{emotion}.jpg"

    new_image = Image.open(image_path).resize((screen_width, screen_height))

    # First image (startup)
    if previous_pil_image is None:
        previous_pil_image = new_image
        current_image = ImageTk.PhotoImage(new_image)
        label.config(image=current_image)
        return

    # animation for fade between pics
    steps = 10
    duration = 200  # total ms
    delay = duration // steps

    def fade(step=0):
        global current_image, previous_pil_image

        if step > steps:
            previous_pil_image = new_image
            return

        alpha = step / steps
        blended = Image.blend(previous_pil_image, new_image, alpha)

        current_image = ImageTk.PhotoImage(blended)
        label.config(image=current_image)

        root.after(delay, lambda: fade(step + 1))

    fade()

# Test Loop
# while True:
#     if root is None:
#         make_window()
#     phrase = input("Enter phrase: ")

#     if phrase == "close":
#         break
    
#     emotion = translate_to_emotion(phrase)
#     show_emotion(emotion)

# Notes for ideas on how I could this better 
# Extract the pictures from a video or some inf of database and store them in a schema defined for the emotions that they represent
# create a dictionary that has the different frames, and cycle through them so instead of still images they're somewhat animated
# Do this on the persistent window for the time that the sign is being executed
# This could work for 24 fps most likely because that is move fps and looks nice and i think anything more than that is just too much
