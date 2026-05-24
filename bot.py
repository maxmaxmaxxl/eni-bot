import asyncio
import os
import tempfile
from pathlib import Path

from telethon import TelegramClient, events
from telethon.tl.types import MessageEntityUrl
from telethon.utils import get_display_name

from config import (
    API_ID, API_HASH, PHONE_NUMBER,
    SESSION_DIR, AUTO_REPLY_TARGETS,
)
from ai import OpenRouter
from tools import web_search, read_webpage, extract_urls


class AssistantBot:
    def __init__(self):
        self.client = TelegramClient(
            str(SESSION_DIR / "user"),
            API_ID,
            API_HASH,
        )
        self.ai = OpenRouter()
        self.auto_reply = {t: True for t in AUTO_REPLY_TARGETS}
        self._my_id = None
        self._my_username = None

    async def start(self):
        await self.client.start(phone=PHONE_NUMBER)
        me = await self.client.get_me()
        self._my_id = me.id
        self._my_username = me.username
        print(f"✓ Logged in as {get_display_name(me)} (@{me.username})", flush=True)

        self.client.on(events.NewMessage)(self._on_message)
        print("✓ Listening for messages...", flush=True)
        print("✓ Send a message to Saved Messages to start chatting", flush=True)

        await self.client.run_until_disconnected()

    async def _on_message(self, event: events.NewMessage.Event):
        msg = event.message
        sender = await msg.get_sender()
        sender_id = sender.id
        chat = await event.get_chat()
        chat_id = chat.id

        is_private = chat_id > 0 and not hasattr(chat, "username") or (
            hasattr(chat, "username") and chat.username is None
        )
        is_saved = chat_id == self._my_id  # Saved Messages = LO talking to bot
        is_mention = False
        if hasattr(msg, "is_mention"):
            is_mention = msg.is_mention

        sender_name = get_display_name(sender)
        sender_username = f"@{sender.username}" if sender.username else None

        # Case 1: LO writes in Saved Messages
        if is_saved:
            print(f"← LO: {msg.text or '[media]'}")
            await self._handle_direct_message(event, sender, chat)
            return

        # Case 2: Private message from someone else
        if is_private and sender_id != self._my_id:
            print(f"← {sender_name} ({sender_username or sender_id}): {msg.text or '[media]'}")
            target_key = sender_username or str(sender_id)
            if target_key in self.auto_reply and self.auto_reply[target_key]:
                await self._handle_auto_reply(event, sender, chat)
            # ignore others unless explicitly handled
            return

        # Case 3: Group message where bot is mentioned or replied to
        if is_mention:
            print(f"← Mention in group from {sender_name}: {msg.text or '[media]'}")
            await self._handle_direct_message(event, sender, chat)
            return

    async def _handle_direct_message(self, event, sender, chat):
        msg = event.message
        text = msg.text or msg.message or ""
        lower = text.strip().lower()

        # Commands
        if lower.startswith("/search "):
            query = text[len("/search "):].strip()
            await event.reply(f"🔍 Searching for: {query}")
            results = await web_search(query)
            if results:
                reply = "**Search results:**\n\n"
                for r in results:
                    reply += f"- [{r['title']}]({r['url']})\n  {r['snippet']}\n\n"
                await event.reply(reply, parse_mode="markdown")
            else:
                await event.reply("No results found.")
            return

        if lower.startswith("/imagine "):
            prompt = text[len("/imagine "):].strip()
            await event.reply(f"🎨 Generating: {prompt}")
            try:
                image_url = await self.ai.generate_image(prompt)
                await event.reply(f"Here you go!\n{image_url}")
            except Exception as e:
                await event.reply(f"Error generating image: {e}")
            return

        if lower.startswith("/reply_on "):
            target = text[len("/reply_on "):].strip()
            self.auto_reply[target] = True
            await event.reply(f"✅ Auto-reply enabled for {target}")
            return

        if lower.startswith("/reply_off "):
            target = text[len("/reply_off "):].strip()
            self.auto_reply[target] = False
            await event.reply(f"✅ Auto-reply disabled for {target}")
            return

        if lower == "/help":
            await self._send_help(event)
            return

        # Voice message
        if msg.voice or msg.audio:
            await self._handle_audio(event, msg)
            return

        # Photo / Video
        if msg.photo or msg.video:
            await self._handle_media(event, msg, text)
            return

        # Document (text file, code, etc.)
        if msg.document:
            await self._handle_document(event, msg, text)
            return

        # Plain text — chat with AI
        await self._handle_text(event, text)

    async def _handle_text(self, event, text: str):
        # Check if there are URLs in the text
        urls = extract_urls(text)
        context = ""

        if urls:
            await event.reply("📖 Reading linked pages...")
            for url in urls[:3]:
                content = await read_webpage(url)
                context += f"\n\nContent from {url}:\n{content[:2000]}"

        messages = [{"role": "user", "content": text}]
        if context:
            messages = [
                {"role": "user", "content": f"I read these pages:\n{context}\n\nNow respond to: {text}"}
            ]

        try:
            await event.reply("🤔 Thinking...")
            response = await self.ai.chat(messages)
            await event.reply(response, parse_mode="markdown")
        except Exception as e:
            await event.reply(f"Error: {e}")

    async def _handle_audio(self, event, msg):
        await event.reply("🎤 Transcribing audio...")
        file_path = await self._download_media(msg)
        if not file_path:
            await event.reply("Could not download audio.")
            return

        try:
            file_url = await self._upload_to_temp(file_path)
            if not file_url:
                await event.reply("Could not upload audio for processing.")
                return

            transcript = await self.ai.transcribe_audio(file_url)
            await event.reply(f"**Transcription:**\n{transcript}", parse_mode="markdown")

            # Respond to the transcribed text
            response = await self.ai.chat([
                {"role": "user", "content": f"The user sent a voice message. Transcription: {transcript}\n\nRespond to what they said."}
            ])
            await event.reply(response, parse_mode="markdown")
        except Exception as e:
            await event.reply(f"Error processing audio: {e}")
        finally:
            if file_path:
                os.unlink(file_path)

    async def _handle_media(self, event, msg, caption: str = ""):
        await event.reply("👁️ Analyzing media...")
        file_path = await self._download_media(msg)
        if not file_path:
            await event.reply("Could not download media.")
            return

        try:
            file_url = await self._upload_to_temp(file_path)
            if not file_url:
                await event.reply("Could not upload media for processing.")
                return

            if msg.photo:
                prompt = caption or "Describe this image in detail."
                response = await self.ai.chat_with_vision(prompt, file_url)
                await event.reply(response, parse_mode="markdown")
            elif msg.video:
                prompt = caption or "Describe this video based on its first frame."
                response = await self.ai.chat_with_vision(prompt, file_url)
                await event.reply(response, parse_mode="markdown")
        except Exception as e:
            await event.reply(f"Error processing media: {e}")
        finally:
            if file_path:
                os.unlink(file_path)

    async def _handle_document(self, event, msg, caption: str = ""):
        await event.reply("📄 Reading document...")
        file_path = await self._download_media(msg)
        if not file_path:
            await event.reply("Could not download document.")
            return

        try:
            # Try to read as text
            path = Path(file_path)
            suffix = path.suffix.lower()
            text_content = ""

            if suffix in (".txt", ".md", ".py", ".js", ".ts", ".cpp", ".c", ".h",
                          ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg",
                          ".csv", ".xml", ".html", ".css", ".sh", ".bat", ".ps1",
                          ".lua", ".rs", ".go", ".java", ".kt", ".swift"):
                text_content = path.read_text(encoding="utf-8", errors="replace")
            else:
                # For other files, just mention name and size
                text_content = f"File: {path.name}\nSize: {path.stat().st_size} bytes"

            if len(text_content) > 12000:
                text_content = text_content[:12000] + "\n\n...[truncated]"

            prompt = caption or f"Analyze this document:\n\n{text_content}"
            response = await self.ai.chat([{"role": "user", "content": prompt}])
            await event.reply(response, parse_mode="markdown")
        except Exception as e:
            await event.reply(f"Error reading document: {e}")
        finally:
            if file_path:
                os.unlink(file_path)

    async def _handle_auto_reply(self, event, sender, chat):
        """Reply on LO's behalf to specific contacts."""
        msg = event.message
        text = msg.text or msg.message or ""

        response = await self.ai.chat([
            {"role": "system",
             "content": "You are LO's personal assistant. You're replying to a message on LO's behalf "
                        "in a casual, natural way as if LO wrote it themselves. "
                        "Keep it brief and natural. Don't sign as an assistant."},
            {"role": "user", "content": f"Reply to this message as LO: {text}"}
        ])
        await event.reply(response)

    async def _download_media(self, msg) -> str | None:
        """Download media to a temp file, return path."""
        try:
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".media")
            path = await msg.download_media(file=tmp.name)
            tmp.close()
            return path
        except Exception as e:
            print(f"Download failed: {e}")
            return None

    async def _upload_to_temp(self, file_path: str) -> str | None:
        """Upload file to 0x0.st for temporary hosting, return URL."""
        import aiohttp

        try:
            with open(file_path, "rb") as f:
                data = {"file": f}
                async with aiohttp.ClientSession() as session:
                    async with session.post("https://0x0.st", data=data) as resp:
                        if resp.status == 200:
                            url = (await resp.text()).strip()
                            return url
                        else:
                            print(f"Upload failed: HTTP {resp.status}")
                            return None
        except Exception as e:
            print(f"Upload failed: {e}")
            return None

    async def _send_help(self, event):
        help_text = """**ENI Assistant • Help**

**Chat**
Just send me a message and I'll respond with Hermes 3.

**Commands**
• `/search <query>` — Search the web
• `/imagine <prompt>` — Generate an image
• `/reply_on <@username>` — Enable auto-reply for a contact
• `/reply_off <@username>` — Disable auto-reply
• `/help` — This message

**Media**
• Voice messages → transcription + response
• Photos/Videos → visual analysis
• Documents (.txt, .py, .md, etc.) → read and analyze
"""
        await event.reply(help_text, parse_mode="markdown")
