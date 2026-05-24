from typing import Optional

import aiohttp

from config import (
    CHAT_MODEL, VISION_MODEL, IMAGE_MODEL, AUDIO_MODEL, SYSTEM_PROMPT,
    OPENROUTER_API_KEY, OPENROUTER_BASE,
)


class AI:
    def __init__(self, groq_key: str):
        self._groq_key = groq_key
        self._session: Optional[aiohttp.ClientSession] = None

    async def _s(self) -> aiohttp.ClientSession:
        if not self._session or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def _groq(self, payload: dict) -> dict:
        s = await self._s()
        headers = {"Authorization": f"Bearer {self._groq_key}", "Content-Type": "application/json"}
        async with s.post("https://api.groq.com/openai/v1/chat/completions", json=payload, headers=headers) as r:
            data = await r.json()
            if "error" in data:
                raise Exception(f"Groq: {data['error']}")
            return data

    async def _openrouter(self, payload: dict) -> dict:
        s = await self._s()
        headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"}
        async with s.post(f"{OPENROUTER_BASE}/chat/completions", json=payload, headers=headers) as r:
            data = await r.json()
            if "error" in data:
                raise Exception(f"OpenRouter: {data['error']}")
            return data

    def _sys(self, messages: list[dict]) -> list[dict]:
        if not messages or messages[0].get("role") != "system":
            messages = [{"role": "system", "content": SYSTEM_PROMPT}] + messages
        return messages

    async def chat(self, messages: list[dict], model: Optional[str] = None, max_tokens: int = 4096, temperature: float = 0.7) -> str:
        messages = self._sys(messages)
        payload = {"model": model or "llama-3.3-70b-versatile", "messages": messages, "max_tokens": max_tokens, "temperature": temperature}
        data = await self._groq(payload)
        return data["choices"][0]["message"]["content"]

    async def chat_with_vision(self, prompt: str, image_url: str, model: Optional[str] = None) -> str:
        model = model or "llama-3.2-90b-vision-preview"
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": [{"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": image_url}}]},
            ],
            "max_tokens": 2048,
        }
        data = await self._groq(payload)
        return data["choices"][0]["message"]["content"]

    async def generate_image(self, prompt: str) -> str:
        s = await self._s()
        headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"}
        payload = {"model": IMAGE_MODEL, "prompt": prompt}
        async with s.post(f"{OPENROUTER_BASE}/images/generations", json=payload, headers=headers) as r:
            data = await r.json()
            return data["data"][0]["url"]

    async def transcribe_audio(self, audio_url: str) -> str:
        s = await self._s()
        headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"}
        payload = {"model": AUDIO_MODEL, "url": audio_url}
        async with s.post(f"{OPENROUTER_BASE}/audio/transcriptions", json=payload, headers=headers) as r:
            data = await r.json()
            return data["text"]
