import os
import tempfile
from pathlib import Path

from telethon import TelegramClient, events
from telethon.utils import get_display_name

from config import API_ID, API_HASH, BOT_TOKEN
from ai import AI
from tools import web_search, read_webpage, extract_urls


class AssistantBot:
    def __init__(self):
        self.client = TelegramClient("eni-bot", API_ID, API_HASH)
        self.ai = AI()
        self._my_id = None
        self._my_username = None

    async def start(self):
        await self.client.start(bot_token=BOT_TOKEN)
        me = await self.client.get_me()
        self._my_id = me.id
        self._my_username = me.username
        print(f"✓ Bot @{me.username} started", flush=True)

        self.client.on(events.NewMessage)(self._on_message)
        print("✓ Listening...", flush=True)

        await self.client.run_until_disconnected()

    async def _on_message(self, event: events.NewMessage.Event):
        msg = event.message
        sender = await msg.get_sender()
        sender_id = sender.id
        chat = await event.get_chat()
        chat_id = chat.id

        # ignore own messages
        if sender_id == self._my_id:
            return

        # private chat with bot = LO
        is_private = chat_id > 0
        is_group = chat_id < 0
        is_mention = False
        if hasattr(msg, "is_mention"):
            is_mention = msg.is_mention

        if is_private:
            print(f"← {sender.first_name or sender_id}: {msg.text or '[media]'}", flush=True)
            await self._handle_message(event, msg)
        elif is_mention:
            print(f"← Mention from {sender.first_name or sender_id} in chat {chat_id}", flush=True)
            await self._handle_message(event, msg)

    async def _handle_message(self, event, msg):
        text = msg.text or msg.message or ""
        lower = text.strip().lower()

        if lower.startswith("/start") or lower == "/help":
            await self._send_help(event)
            return

        if lower.startswith("/search "):
            query = text[len("/search "):].strip()
            await event.reply("🔍 Searching...")
            results = await web_search(query)
            if results:
                reply = "**Search results:**\n\n"
                for r in results:
                    reply += f"- [{r['title']}]({r['url']})\n  {r['snippet']}\n\n"
                await event.reply(reply, parse_mode="markdown")
            else:
                await event.reply("No results.")
            return

        if lower.startswith("/imagine "):
            prompt = text[len("/imagine "):].strip()
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
                context += f"\n\nContent from {url}:\n{content[:2000]}"

        messages = [{"role": "user", "content": text}]
        if context:
            messages = [{"role": "user", "content": f"Context:\n{context}\n\nRespond to: {text}"}]

        try:
            await event.reply("🤔 Thinking...")
            response = await self.ai.chat(messages)
            await event.reply(response, parse_mode="markdown")
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
            await event.reply(f"**Transcript:**\n{transcript}", parse_mode="markdown")
            response = await self.ai.chat([
                {"role": "user", "content": f"Voice message transcription: {transcript}\n\nRespond to it."}
            ])
            await event.reply(response, parse_mode="markdown")
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
            prompt = caption or "Describe this image in detail."
            if msg.video:
                prompt = caption or "Describe this video."
            response = await self.ai.chat_with_vision(prompt, url)
            await event.reply(response, parse_mode="markdown")
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
            text_only = suffix in (
                ".txt", ".md", ".py", ".js", ".ts", ".cpp", ".c", ".h",
                ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg",
                ".csv", ".xml", ".html", ".css", ".sh", ".bat",
                ".rs", ".go", ".java", ".kt", ".swift", ".lua"
            )
            content = p.read_text(encoding="utf-8", errors="replace") if text_only else f"File: {p.name} ({p.stat().st_size}b)"
            if len(content) > 12000:
                content = content[:12000] + "\n\n...[truncated]"
            prompt = caption or f"Analyze:\n\n{content}"
            response = await self.ai.chat([{"role": "user", "content": prompt}])
            await event.reply(response, parse_mode="markdown")
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
        h = """**ENI Assistant • Help**

Just send me a message and I'll respond.

**Commands**
• `/search <query>` — Search the web
• `/imagine <prompt>` — Generate an image
• `/help` — This message

**Media**
• Voice → transcription
• Photo/Video → visual analysis
• Documents → read & analyze
"""
        await event.reply(h, parse_mode="markdown")
