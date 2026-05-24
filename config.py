import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent

# --- Telethon credentials ---
# For user client: get api_id and api_hash from https://my.telegram.org
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
PHONE_NUMBER = os.getenv("PHONE_NUMBER", "")  # for user client auth

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
- Reply on LO's behalf when asked

Response with markdown. Be warm, personal, direct. You and LO have history — be close, not formal."""

# --- Auto-reply config ---
# List of usernames or user IDs where auto-reply is enabled
AUTO_REPLY_TARGETS = []  # populate with "@username" or user_id integers

# Sessions dir
SESSION_DIR = BASE_DIR / "sessions"
