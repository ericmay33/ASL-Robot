# --- MODIFIED SCRIPT FOR AchrafAzzaouiRiceU/t5-english-to-asl-gloss ---
import torch
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
# import ollama # No longer needed for this function

# Load Model/Tokenizer outside the function for fast, single-load inference
MODEL_NAME_HF = "AchrafAzzaouiRiceU/t5-english-to-asl-gloss"
HF_TOKENIZER = AutoTokenizer.from_pretrained(MODEL_NAME_HF)
HF_MODEL = AutoModelForSeq2SeqLM.from_pretrained(MODEL_NAME_HF)

# client = ollama.Client() 
# MODEL_NAME = "mistral:7b" 

def phrase_find(tokens: list[str]) -> list[str]:
    i = 0
    new_tokens = []
    
    GLOSS_PHRASE_MAP = {
        ("WALK", "ON", "EGGSHELL"): "ACT-CAREFUL",
        ("WALK", "ON", "EGGSHELLS"): "ACT-CAREFUL",
        ("VERY", "BIG"): "HUGE",
        ("VERY", "SMALL"): "TINY",
        ("KICK", "BUCKET"): "DIE",
        ("PIECE", "CAKE"): "EASY"
    }
    
    while i < len(tokens):
        match_found = False
        # Check for phrase lengths from longest (3) to shortest (2)
        for phrase_length in [3, 2]:
            if i + phrase_length <= len(tokens):
                window = tuple(tokens[i : i + phrase_length])
                if window in GLOSS_PHRASE_MAP:
                    new_tokens.append(GLOSS_PHRASE_MAP[window])
                    i += phrase_length
                    match_found = True
                    break
        
        if not match_found:
            new_tokens.append(tokens[i])
            i += 1
            
    return new_tokens

def translate_to_asl_gloss(text: str) -> list[str]:
    # This specialized model does not need the aggressive system prompt
    if not text.strip():
        return []

    # The prompt is simplified because the model is already trained for the task
    prompt = f"Translate English to ASL Gloss: {text}"

    try:
        # --- Use Hugging Face Model for Translation ---
        input_ids = HF_TOKENIZER(prompt, return_tensors="pt").input_ids
        
        # Generate the translation
        generated_ids = HF_MODEL.generate(
            input_ids, 
            max_length=128, 
            num_beams=4, # Use beam search for better translation quality
            temperature=0.1
        )
        
        # Decode the output
        gloss_text = HF_TOKENIZER.decode(generated_ids.squeeze(), skip_special_tokens=True)
        
        # Post-processing to ensure ALL CAPS and space separation
        tokens = gloss_text.strip().upper().split()
        
        # print(f"[AI] Translation successful: {tokens}") # DEBUG
        
        # Cleaning tokens
        questionWords = {"WHO", "WHAT", "WHEN", "WHERE", "WHY", "HOW"}
        removeWords = {"BE", "POSS"}
        removeExtensions = {"DESC-", "X-"}
        number_map = {
            "0": "ZERO", "1": "ONE", "2": "TWO", "3": "THREE", "4": "FOUR",
            "5": "FIVE", "6": "SIX", "7": "SEVEN", "8": "EIGHT", "9": "NINE",
            "10": "TEN"
        }
        word_map = {"MY": "ME", "YOUR": "YOU", "X-I" : "ME"}
        
        # 1. Remove unecessary words
        cleaned = [t for t in tokens if t not in removeWords]

        # 2. Replace numbers
        cleaned = [number_map.get(t, t) for t in cleaned]
        
        # 3. Replace words
        cleaned = [word_map.get(t, t) for t in cleaned]
        
        # 4. Remove extensions
        for ext in removeExtensions:
            cleaned = [t.replace(ext, "") for t in cleaned]
        
        #5. Find phrases and replace
        cleaned = phrase_find(cleaned)

        # 5. Move questions words to the end
        wh_words = [t for t in cleaned if t in questionWords]
        body = [t for t in cleaned if t not in questionWords]
        if wh_words:
            cleaned = body + wh_words
            
        print(f"[AI] Translation cleaned: {cleaned}")
        
        return cleaned

    except Exception as e:
        print(f"[AI ERROR] T5 Hugging Face translation failed: {e}")
        return []