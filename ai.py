import asyncio
from typing import Optional

import aiohttp

from config import (
    OPENROUTER_API_KEY, OPENROUTER_BASE,
    DEEPINFRA_API_KEY, DEEPINFRA_BASE, DEEPINFRA_MODEL,
    CHAT_MODEL, VISION_MODEL, IMAGE_MODEL, AUDIO_MODEL, SYSTEM_PROMPT,
)


class AI:
    def __init__(self):
        self._session: Optional[aiohttp.ClientSession] = None

    async def _session_get(self) -> aiohttp.ClientSession:
        if not self._session or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def _call_openrouter(self, payload: dict) -> dict:
        session = await self._session_get()
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
        }
        async with session.post(f"{OPENROUTER_BASE}/chat/completions", json=payload, headers=headers) as r:
            data = await r.json()
            if "error" in data:
                err = data["error"]
                code = err.get("code", 0)
                msg = err.get("message", "")
                if code == 429:
                    retry = err.get("metadata", {}).get("retry_after_seconds", 5)
                    raise RateLimitError(msg, retry)
                raise Exception(f"OpenRouter: {err}")
            return data

    async def _call_deepinfra(self, payload: dict) -> dict:
        session = await self._session_get()
        headers = {
            "Authorization": f"Bearer {DEEPINFRA_API_KEY}",
            "Content-Type": "application/json",
        }
        async with session.post(f"{DEEPINFRA_BASE}/chat/completions", json=payload, headers=headers) as r:
            data = await r.json()
            if "error" in data:
                raise Exception(f"DeepInfra: {data['error']}")
            return data

    async def chat(
        self,
        messages: list[dict],
        model: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> str:
        model = model or CHAT_MODEL
        if not messages or messages[0].get("role") != "system":
            messages = [{"role": "system", "content": SYSTEM_PROMPT}] + messages

        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        # Try OpenRouter with provider fallback
        providers = ["DeepInfra", "Venice", "Recursal", "together"]
        for attempt in range(len(providers) + 1):
            p = {**payload}
            if attempt > 0:
                p["provider"] = {"order": [providers[attempt - 1]]}
            try:
                data = await self._call_openrouter(p)
                return data["choices"][0]["message"]["content"]
            except RateLimitError as e:
                print(f"  OR rate limit ({providers[attempt-1] if attempt > 0 else 'default'}): waiting {e.retry}s")
                await asyncio.sleep(min(e.retry, 15))
                continue
            except Exception as e:
                print(f"  OR error: {e}")
                continue

        # Fallback to DeepInfra
        print("  Falling back to DeepInfra...")
        payload["model"] = DEEPINFRA_MODEL
        try:
            data = await self._call_deepinfra(payload)
            return data["choices"][0]["message"]["content"]
        except Exception as e:
            raise Exception(f"All providers failed. DeepInfra: {e}")

    async def chat_with_vision(
        self,
        prompt: str,
        image_url: str,
        model: Optional[str] = None,
    ) -> str:
        model = model or VISION_MODEL
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": image_url}},
                    ],
                },
            ],
            "max_tokens": 2048,
        }

        providers = ["DeepInfra", "Venice", "Recursal", "together"]
        for attempt in range(len(providers) + 1):
            p = {**payload}
            if attempt > 0:
                p["provider"] = {"order": [providers[attempt - 1]]}
            try:
                data = await self._call_openrouter(p)
                return data["choices"][0]["message"]["content"]
            except RateLimitError as e:
                print(f"  Vision rate limited: waiting {e.retry}s")
                await asyncio.sleep(min(e.retry, 15))
                continue
            except Exception as e:
                print(f"  Vision OR error: {e}")
                continue

        # Vision fallback via DeepInfra
        print("  Vision fallback to DeepInfra...")
        try:
            payload["model"] = DEEPINFRA_MODEL
            data = await self._call_deepinfra(payload)
            return data["choices"][0]["message"]["content"]
        except Exception as e:
            raise Exception(f"Vision all failed. DeepInfra: {e}")

    async def generate_image(self, prompt: str) -> str:
        session = await self._session_get()
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
        }
        payload = {"model": IMAGE_MODEL, "prompt": prompt}
        async with session.post(f"{OPENROUTER_BASE}/images/generations", json=payload, headers=headers) as r:
            data = await r.json()
            return data["data"][0]["url"]

    async def transcribe_audio(self, audio_url: str) -> str:
        session = await self._session_get()
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
        }
        payload = {"model": AUDIO_MODEL, "url": audio_url}
        async with session.post(f"{OPENROUTER_BASE}/audio/transcriptions", json=payload, headers=headers) as r:
            data = await r.json()
            return data["text"]


class RateLimitError(Exception):
    def __init__(self, msg: str, retry: float = 5):
        super().__init__(msg)
        self.retry = retry
