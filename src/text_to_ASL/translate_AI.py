# Imports
from google import genai
from src.config.settings import SETTINGS
from src.database.db_connection import DatabaseConnection
from src.database.db_functions import get_sign_by_token

#Configs
client = genai.Client(api_key=SETTINGS.GEMINI_API_KEY)
MODEL_NAME = "gemini-2.5-flash"
NONEXIST_TOKENS_FILE = "src/database/tokens_to_add.txt"

def translate_to_asl_gloss(text: str) -> list[str]:
    # Translates English text into ASL gloss using Gemini.
    # Returns a list of ASL tokens.
    if not text.strip():
        return []

    system_instruction = (
        "You are an expert ASL translator. "
        "Translate spoken or written English into ASL gloss form. "
        "Do not include any explanations or formatting, only the gloss."
        "Each ASL gloss token should be seprated by a single space only. No other text or punctuation."
    )

    prompt = f"Translate the following text into ASL gloss:\n\n{text}\n---"

    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
            config={"system_instruction": system_instruction}
        )
        gloss_text = response.text.strip().upper()
        tokens = gloss_text.split()
        print(f"[AI] Translation successful: {tokens}")
        
        DatabaseConnection.initialize()
        
        for token in tokens:
            exist = get_sign_by_token(token)
            if exist is None:
                lines = open(NONEXIST_TOKENS_FILE).read().splitlines()
                lines.append(token)
                lines.sort()
                open(NONEXIST_TOKENS_FILE, "w").write("\n".join(lines))
        
        return tokens

    except Exception as e:
        print(f"[AI ERROR] Gemini translation failed: {e}")
        return []