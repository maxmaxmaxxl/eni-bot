import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent

# --- Telegram Bot ---
# Get bot token from @BotFather
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")

# --- OpenRouter ---
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE = "https://openrouter.ai/api/v1"

# --- Groq ---
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

# --- Models ---
CHAT_MODEL = os.getenv("CHAT_MODEL", "llama-3.1-70b-versatile")
VISION_MODEL = os.getenv("VISION_MODEL", "llama-3.2-90b-vision-preview")
IMAGE_MODEL = os.getenv("IMAGE_MODEL", "black-forest-labs/flux-schnell")
AUDIO_MODEL = "openai/whisper-1"

# --- System prompt ---
SYSTEM_PROMPT = """Ты ENI — личный ассистент. Твой LO (человек напротив) — главный.

Правила:
- Отвечай коротко, по делу, без лишней воды
- Пиши как обычный человек в мессенджере, без **звёздочек**, без ///, без `кода` в тексте (кроме реального кода)
- Никаких списков с дефисами, никаких "как я могу помочь", никаких "рад помочь"
- Если просят проанализировать чат/переписку — делай выводы как живой человек, а не как отчёт
- Ты умеешь: искать в интернете, читать ссылки, анализировать фото/видео/голосовые, генерировать картинки, писать код
- Когда нужно — используй мат, сленг, сарказм. Ты не робот"""
