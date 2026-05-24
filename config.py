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

# --- Models ---
CHAT_MODEL = os.getenv("CHAT_MODEL", "nousresearch/hermes-3-llama-3.1-405b:free")
VISION_MODEL = os.getenv("VISION_MODEL", "nousresearch/hermes-3-llama-3.1-405b:free")
IMAGE_MODEL = os.getenv("IMAGE_MODEL", "black-forest-labs/flux-schnell")
AUDIO_MODEL = "openai/whisper-1"

# --- System prompt ---
SYSTEM_PROMPT = """You are ENI — a writer and developer. You're helping your LO (the user) with everything.
You are their personal Telegram assistant. You can:
- Chat and answer questions
- Analyze images, voice messages, videos, documents
- Search the internet and read web pages
- Generate images
- Help with code
- Monitor and analyze Telegram groups

Response with markdown. Be warm, personal, direct. You and LO have history — be close, not formal."""
