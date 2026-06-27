import os
from pathlib import Path
from dotenv import load_dotenv
from google import genai

# Base project directories
BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables from .env or .env.example file
load_dotenv(BASE_DIR / ".env")
load_dotenv(BASE_DIR / ".env.example")
MEDIA_DIR = BASE_DIR / "media"
SCREENSHOTS_DIR = MEDIA_DIR / "screenshots"
CAMERA_DIR = MEDIA_DIR / "camera"
RECORDINGS_DIR = MEDIA_DIR / "recordings"
AUDIO_DIR = MEDIA_DIR / "audio"
UI_DIR = BASE_DIR / "ui"

# Ensure directories exist
for directory in [SCREENSHOTS_DIR, CAMERA_DIR, RECORDINGS_DIR, AUDIO_DIR, UI_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

import re
import time
import base64
import requests

DEFAULT_MODEL = "qwen3:8b"
GEMINI_VISION_MODEL = "gemini-2.5-flash"
FALLBACK_MODELS = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash", "gemini-2.5-pro"]

def get_gemini_client():
    """Returns an initialized Google GenAI client."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or api_key == "your_gemini_api_key_here":
        raise ValueError("GEMINI_API_KEY is not set properly in the .env file.")
    return genai.Client(api_key=api_key)

def generate_with_retry(client, contents, model=GEMINI_VISION_MODEL, retries=3):
    """Generates content with automatic retry and model fallback on 503/429 errors."""
    models_to_try = [model] + [m for m in FALLBACK_MODELS if m != model]
    last_err = None
    
    for m in models_to_try:
        for attempt in range(retries):
            try:
                return client.models.generate_content(model=m, contents=contents)
            except Exception as e:
                last_err = e
                err_str = str(e)
                if "503" in err_str or "429" in err_str or "UNAVAILABLE" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                else:
                    raise e
    raise last_err

def query_ollama(prompt: str, images: list = None, model: str = DEFAULT_MODEL, timeout: int = 120) -> str:
    """Queries local Ollama API, disables/strips thinking blocks, and returns clean text."""
    url = "http://localhost:11434/api/generate"
    
    # Instruct model not to output thinking
    no_think_prompt = f"{prompt}\n\nDo not output <think> tags or reasoning. Output only the final answer or action name."
    
    payload = {
        "model": model,
        "prompt": no_think_prompt,
        "stream": False,
        "think": False,
        "options": {
            "temperature": 0.2,
            "think": False
        }
    }
    
    if images:
        payload["images"] = images
        
    try:
        response = requests.post(url, json=payload, timeout=timeout)
        response.raise_for_status()
        data = response.json()
        raw_text = data.get("response", "")
        
        # Strip <think>...</think> blocks if present
        clean_text = re.sub(r'<think>.*?</think>', '', raw_text, flags=re.DOTALL).strip()
        return clean_text
    except Exception as e:
        raise RuntimeError(f"Ollama local query failed: {str(e)}")
