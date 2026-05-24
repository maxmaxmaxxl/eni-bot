import asyncio
import os
import tempfile
from pathlib import Path

from telethon import TelegramClient, events
from telethon.utils import get_display_name

from config import API_ID, API_HASH, BOT_TOKEN, GROQ_API_KEY
from ai import AI
from tools import web_search, read_webpage, extract_urls

SESSION_DIR = Path(__file__).parent / "sessions"


class AssistantBot:
    def __init__(self):
        self.bot = TelegramClient("eni-bot", API_ID, API_HASH)
        self.user = TelegramClient(str(SESSION_DIR / "user"), API_ID, API_HASH)
        self.ai = AI(groq_key=GROQ_API_KEY)
        self._my_id = None
        self._my_username = None
        self._lo_id = None

    async def start(self):
        # Start user client
        await self.user.start()
        me_user = await self.user.get_me()
        self._lo_id = me_user.id
        print(f"✓ User client: {me_user.first_name} ({me_user.phone})", flush=True)

        # Start bot client
        await self.bot.start(bot_token=BOT_TOKEN)
        me_bot = await self.bot.get_me()
        self._my_id = me_bot.id
        print(f"✓ Bot @{me_bot.username} started", flush=True)

        # Listeners
        self.bot.on(events.NewMessage)(self._on_bot_msg)
        self.user.on(events.NewMessage)(self._on_incoming_msg)
        print("✓ Listening for messages and analyzing...", flush=True)

        await asyncio.gather(
            self.bot.run_until_disconnected(),
            self.user.run_until_disconnected(),
        )

    # ── Bot handler (LO talks to bot) ──
    async def _on_bot_msg(self, event):
        msg = event.message
        sender = await msg.get_sender()
        if sender.id == self._my_id:
            return
        chat_id = (await event.get_chat()).id

        is_private = chat_id > 0
        is_mention = getattr(msg, "is_mention", False)

        if is_private or is_mention:
            print(f"← Bot msg: {sender.first_name}: {msg.text or '[media]'}", flush=True)
            await self._handle_message(event, msg)

    # ── User client handler (LO's incoming messages) ──
    async def _on_incoming_msg(self, event):
        msg = event.message
        sender = await msg.get_sender()
        if sender.id == self._lo_id:
            return  # skip LO's own messages
        chat = await event.get_chat()
        chat_id = chat.id

        # Only private chats, not groups, not bots
        if chat_id < 0:
            return
        if getattr(sender, "bot", False):
            return

        sender_name = get_display_name(sender)
        text = msg.text or msg.message or "[media]"
        print(f"→ Incoming from {sender_name}: {text}", flush=True)

        # Analyze silently
        asyncio.ensure_future(self._analyze_and_report(sender_name, sender.id, text))

    async def _analyze_and_report(self, name: str, uid: int, text: str):
        try:
            chat_info = f"@{name} (id:{uid})" if name else f"id:{uid}"
            prompt = (
                f"Тебе пришло сообщение от {chat_info}. "
                f"Текст: {text}\n\n"
                f"Коротко: кто это скорее всего, о чём речь, важное ли сообщение, "
                f"стоит ли ответить? Если это реклама/спам — просто промолчи. "
                f"Ответь коротко, только если это действительно важно или интересно."
            )
            response = await self.ai.chat(
                [{"role": "user", "content": prompt}],
                max_tokens=300,
            )

            # If AI says it's important — send to LO
            if response and not response.startswith("не "):
                await self.bot.send_message(
                    self._lo_id,
                    f"📩 {name} пишет:\n{response}",
                )
        except Exception as e:
            print(f"Analyze error: {e}", flush=True)

    # ── Message handling (same as before) ──
    async def _handle_message(self, event, msg):
        text = msg.text or msg.message or ""
        lower = text.strip().lower()

        if lower.startswith("/start") or lower == "/help":
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

/search <query> — search web
/imagine <prompt> — generate image
/help — this

Voice → transcribe
Photo/Video → analyze
Documents → read + analyze

I also silently analyze your incoming messages and alert you if important."""
        await event.reply(h)
