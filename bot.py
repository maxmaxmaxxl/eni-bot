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
        self._lo_id = None

    async def start(self):
        # User client (for analyzing LO's incoming messages)
        await self.user.start()
        me_user = await self.user.get_me()
        self._lo_id = me_user.id
        print(f"✓ User: {me_user.first_name}", flush=True)

        # Bot client (for talking to LO)
        await self.bot.start(bot_token=BOT_TOKEN)
        me_bot = await self.bot.get_me()
        self._my_id = me_bot.id
        print(f"✓ Bot @{me_bot.username} started", flush=True)

        self.bot.on(events.NewMessage)(self._on_bot_msg)
        self.user.on(events.NewMessage)(self._on_incoming)
        print("✓ Listening + analyzing DMs...", flush=True)

        await asyncio.gather(
            self.bot.run_until_disconnected(),
            self.user.run_until_disconnected(),
        )

    # ─── Bot: LO talks here ───
    async def _on_bot_msg(self, event):
        msg = event.message
        sender = await msg.get_sender()
        if sender.id == self._my_id:
            return
        chat_id = (await event.get_chat()).id
        if chat_id > 0 or getattr(msg, "is_mention", False):
            print(f"← {sender.first_name}: {msg.text or '[media]'}", flush=True)
            await self._handle_message(event, msg)

    # ─── User client: LO's DMs being analyzed ───
    async def _on_incoming(self, event):
        msg = event.message
        sender = await msg.get_sender()
        if sender.id == self._lo_id or getattr(sender, "bot", False):
            return
        chat = await event.get_chat()
        if chat.id < 0:
            return

        name = get_display_name(sender)
        text = msg.text or msg.message or "[media]"
        print(f"→ DM from {name}: {text}", flush=True)
        asyncio.ensure_future(self._analyze(name, text))

    async def _analyze(self, name: str, text: str):
        try:
            r = await self.ai.chat([
                {"role": "system", "content": "Ты анализируешь входящие сообщения LO. Если сообщение важное/срочное/интересное — напиши LO краткий анализ. Если реклама, спам, ерунда — ничего не пиши."},
                {"role": "user", "content": f"Сообщение от {name}: {text}\n\nЧто скажешь?"}
            ], max_tokens=300)
            if r and len(r) > 10:
                await self.bot.send_message(self._lo_id, f"📩 {name} пишет:\n{r}")
        except Exception as e:
            print(f"Analyze err: {e}", flush=True)

    # ─── Message handlers ───
    async def _handle_message(self, event, msg):
        text = msg.text or msg.message or ""
        lower = text.strip().lower()

        if lower == "/start" or lower == "/help":
            await self._send_help(event)
            return
        if lower.startswith("/search "):
            q = text[8:].strip()
            await event.reply("🔍 Searching...")
            r = await web_search(q)
            if r:
                reply = "Results:\n\n" + "\n\n".join(f"- {x['title']}: {x['url']}\n  {x['snippet']}" for x in r)
                await event.reply(reply)
            else:
                await event.reply("Nothing.")
            return
        if lower.startswith("/imagine "):
            p = text[9:].strip()
            await event.reply("🎨 Generating...")
            try:
                url = await self.ai.generate_image(p)
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
        ctx = ""
        if urls:
            await event.reply("📖 Reading...")
            for url in urls[:3]:
                ctx += f"\n\nFrom {url}:\n{(await read_webpage(url))[:2000]}"
        msgs = [{"role": "user", "content": text}]
        if ctx:
            msgs = [{"role": "user", "content": f"Context:{ctx}\n\nNow: {text}"}]
        try:
            await event.reply("🤔 Thinking...")
            await event.reply(await self.ai.chat(msgs))
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
            t = await self.ai.transcribe_audio(url)
            await event.reply(f"Transcript:\n{t}")
            r = await self.ai.chat([{"role": "user", "content": f"Voice: {t}\n\nRespond."}])
            await event.reply(r)
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
            p = caption or "Describe in detail."
            if msg.video:
                p = caption or "Describe this video."
            await event.reply(await self.ai.chat_with_vision(p, url))
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
            ext = p.suffix.lower()
            text_exts = {".txt", ".md", ".py", ".js", ".ts", ".cpp", ".c", ".h",
                         ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg",
                         ".csv", ".xml", ".html", ".css", ".sh", ".bat",
                         ".rs", ".go", ".java", ".kt", ".swift", ".lua"}
            content = p.read_text(encoding="utf-8", errors="replace") if ext in text_exts else f"File: {p.name} ({p.stat().st_size}b)"
            if len(content) > 12000:
                content = content[:12000] + "\n...[truncated]"
            await event.reply(await self.ai.chat([{"role": "user", "content": caption or f"Analyze:\n\n{content}"}]))
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
        await event.reply(
            "ENI Assistant\n\n"
            "Just send me a message.\n"
            "/search <q> - web search\n"
            "/imagine <p> - generate image\n"
            "/help - this\n\n"
            "I also analyze your DMs silently."
        )
