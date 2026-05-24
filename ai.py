import aiohttp
import json
import base64
import random
from typing import Optional


class RateLimitError(Exception):
    pass
from config import (
    OPENROUTER_API_KEY, OPENROUTER_BASE,
    CHAT_MODEL, VISION_MODEL, IMAGE_MODEL, AUDIO_MODEL, SYSTEM_PROMPT
)


class OpenRouter:
    def __init__(self):
        self.headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
        }

    PROVIDERS = ["DeepInfra", "Venice", "Recursal", "together"]

    async def _post(self, endpoint: str, payload: dict, retry_provider: bool = True) -> dict:
        url = f"{OPENROUTER_BASE}/{endpoint}"
        async with aiohttp.ClientSession(headers=self.headers) as session:
            async with session.post(url, json=payload) as resp:
                data = await resp.json()
                if "error" in data:
                    err = data["error"]
                    code = err.get("code", 0)
                    msg = err.get("message", "")
                    if code == 429 and retry_provider:
                        raise RateLimitError(msg)
                    raise Exception(f"OpenRouter error: {err}")
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

        providers = self.PROVIDERS.copy()
        last_err = None
        for attempt in range(len(providers) + 1):
            payload = {
                "model": model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
            if attempt > 0:
                # try a different provider
                provider = providers[attempt - 1]
                payload["provider"] = {"order": [provider]}

            try:
                data = await self._post("chat/completions", payload, retry_provider=(attempt == 0))
                return data["choices"][0]["message"]["content"]
            except RateLimitError as e:
                last_err = e
                continue

        raise Exception(f"All providers rate limited. Last: {last_err}")

    async def chat_with_vision(
        self,
        prompt: str,
        image_url: str,
        model: Optional[str] = None,
    ) -> str:
        model = model or VISION_MODEL
        providers = self.PROVIDERS.copy()
        for attempt in range(len(providers) + 1):
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
            if attempt > 0:
                payload["provider"] = {"order": [providers[attempt - 1]]}
            try:
                data = await self._post("chat/completions", payload, retry_provider=(attempt == 0))
                return data["choices"][0]["message"]["content"]
            except RateLimitError:
                continue
        raise Exception("All providers rate limited for vision")

    async def generate_image(self, prompt: str) -> str:
        data = await self._post("images/generations", {
            "model": IMAGE_MODEL,
            "prompt": prompt,
        })
        return data["data"][0]["url"]

    async def transcribe_audio(self, audio_url: str) -> str:
        data = await self._post("audio/transcriptions", {
            "model": AUDIO_MODEL,
            "url": audio_url,
        })
        return data["text"]

    def _build_search_tool(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": "web_search",
                "description": "Search the internet for current information",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query"
                        }
                    },
                    "required": ["query"]
                }
            }
        }

    def _build_webpage_tool(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": "read_webpage",
                "description": "Read and extract content from a web page",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "URL to read"
                        }
                    },
                    "required": ["url"]
                }
            }
        }

    async def chat_with_tools(
        self,
        messages: list[dict],
        tools: list[str],
    ) -> dict:
        payload = {
            "model": CHAT_MODEL,
            "messages": messages,
            "max_tokens": 4096,
        }
        tool_defs = []
        if "web_search" in tools:
            tool_defs.append(self._build_search_tool())
        if "read_webpage" in tools:
            tool_defs.append(self._build_webpage_tool())
        if tool_defs:
            payload["tools"] = tool_defs

        data = await self._post("chat/completions", payload)
        return data["choices"][0]["message"]
