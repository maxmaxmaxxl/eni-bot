import os
import tempfile
from pathlib import Path

from telethon import TelegramClient, events
from telethon.utils import get_display_name

from config import API_ID, API_HASH, BOT_TOKEN, GROQ_API_KEY
from ai import AI
from tools import web_search, read_webpage, extract_urls


class AssistantBot:
    def __init__(self):
        self.client = TelegramClient("eni-bot", API_ID, API_HASH)
        self.ai = AI(groq_key=GROQ_API_KEY)
        self._my_id = None

    async def start(self):
        await self.client.start(bot_token=BOT_TOKEN)
        me = await self.client.get_me()
        self._my_id = me.id
        print(f"✓ Bot @{me.username} started", flush=True)

        self.client.on(events.NewMessage)(self._on_message)
        print("✓ Listening...", flush=True)

        await self.client.run_until_disconnected()

    async def _on_message(self, event):
        msg = event.message
        sender = await msg.get_sender()
        if sender.id == self._my_id:
            return
        chat_id = (await event.get_chat()).id
        is_private = chat_id > 0
        is_mention = getattr(msg, "is_mention", False)
        if is_private or is_mention:
            print(f"← {sender.first_name or sender.id}: {msg.text or '[media]'}", flush=True)
            await self._handle_message(event, msg)

    async def _handle_message(self, event, msg):
        text = msg.text or msg.message or ""
        lower = text.strip().lower()

        if lower == "/start" or lower == "/help":
            await self._send_help(event)
            return

        if lower.startswith("/search "):
            query = text[8:].strip()
            await event.reply("🔍 Searching...")
            results = await web_search(query)
            if results:
                reply = "Search results:\n\n"
                for r in results:
                    reply += f"- {r['title']}: {r['url']}\n  {r['snippet']}\n\n"
                await event.reply(reply)
            else:
                await event.reply("Nothing found.")
            return

        if lower.startswith("/imagine "):
            prompt = text[9:].strip()
            await event.reply("🎨 Generating...")
            try:
                url = await self.ai.generate_image(prompt)
                await event.reply(url)
            except Exception as e:
                await event.reply(f"Error: {e}")
            return

        if msg.voice or msg.audio:
            await self._handle_audio(event, msg)
            return

        if msg.photo or msg.video:
            await self._handle_media(event, msg, text)
            return

        if msg.document:
            await self._handle_document(event, msg, text)
            return

        await self._handle_text(event, text)

    async def _handle_text(self, event, text: str):
        urls = extract_urls(text)
        context = ""
        if urls:
            await event.reply("📖 Reading links...")
            for url in urls[:3]:
                content = await read_webpage(url)
                context += f"\n\nFrom {url}:\n{content[:2000]}"

        messages = [{"role": "user", "content": text}]
        if context:
            messages = [{"role": "user", "content": f"Context:\n{context}\n\nNow: {text}"}]

        try:
            await event.reply("🤔 Thinking...")
            response = await self.ai.chat(messages)
            await event.reply(response)
        except Exception as e:
            await event.reply(f"Error: {e}")

    async def _handle_audio(self, event, msg):
        await event.reply("🎤 Transcribing...")
        path = await self._download(msg)
        if not path:
            return
        try:
            url = await self._upload_to_temp(path)
            if not url:
                await event.reply("Upload failed.")
                return
            transcript = await self.ai.transcribe_audio(url)
            await event.reply(f"Transcript:\n{transcript}")
            response = await self.ai.chat([
                {"role": "user", "content": f"Voice: {transcript}\n\nRespond."}
            ])
            await event.reply(response)
        finally:
            if path:
                os.unlink(path)

    async def _handle_media(self, event, msg, caption: str = ""):
        await event.reply("👁️ Analyzing...")
        path = await self._download(msg)
        if not path:
            return
        try:
            url = await self._upload_to_temp(path)
            if not url:
                await event.reply("Upload failed.")
                return
            prompt = caption or "Describe in detail."
            if msg.video:
                prompt = caption or "Describe this video."
            response = await self.ai.chat_with_vision(prompt, url)
            await event.reply(response)
        finally:
            if path:
                os.unlink(path)

    async def _handle_document(self, event, msg, caption: str = ""):
        await event.reply("📄 Reading...")
        path = await self._download(msg)
        if not path:
            return
        try:
            p = Path(path)
            suffix = p.suffix.lower()
            text_exts = {
                ".txt", ".md", ".py", ".js", ".ts", ".cpp", ".c", ".h",
                ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg",
                ".csv", ".xml", ".html", ".css", ".sh", ".bat",
                ".rs", ".go", ".java", ".kt", ".swift", ".lua",
            }
            content = p.read_text(encoding="utf-8", errors="replace") if suffix in text_exts else f"File: {p.name} ({p.stat().st_size}b)"
            if len(content) > 12000:
                content = content[:12000] + "\n\n...[truncated]"
            prompt = caption or f"Analyze:\n\n{content}"
            response = await self.ai.chat([{"role": "user", "content": prompt}])
            await event.reply(response)
        finally:
            if path:
                os.unlink(path)

    async def _download(self, msg) -> str | None:
        try:
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".media")
            return await msg.download_media(file=tmp.name)
        except Exception as e:
            print(f"Download error: {e}")
            return None

    async def _upload_to_temp(self, path: str) -> str | None:
        import aiohttp
        try:
            with open(path, "rb") as f:
                form = aiohttp.FormData()
                form.add_field("file", f)
                async with aiohttp.ClientSession() as sess:
                    async with sess.post("https://tmpfiles.org/api/v1/upload", data=form) as resp:
                        if resp.status == 200:
                            j = await resp.json()
                            return j.get("data", {}).get("url")
            return None
        except Exception as e:
            print(f"Upload error: {e}")
            return None

    async def _send_help(self, event):
        h = """ENI Assistant

Just send me a message, I'll respond.

/search <query> - search web
/imagine <prompt> - generate image
/help - this

Voice -> transcribe
Photo/Video -> analyze
Documents -> read + analyze"""
        await event.reply(h)
