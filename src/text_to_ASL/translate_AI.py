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
        removeWords = {"BE"}
        removeExtensions = {"DESC-", "X-"}
        
        # 1. Remove unecessary words
        cleaned = [t for t in tokens if t not in removeWords]

        # 2. Remove extensions
        for ext in removeExtensions:
            cleaned = [t.replace(ext, "") for t in cleaned]

        # 3. Move questions words to the end
        wh_words = [t for t in cleaned if t in questionWords]
        body = [t for t in cleaned if t not in questionWords]
        if wh_words:
            cleaned = body + wh_words
            
        print(f"[AI] Translation cleaned: {cleaned}")
        
        return cleaned

    except Exception as e:
        print(f"[AI ERROR] T5 Hugging Face translation failed: {e}")
        return []