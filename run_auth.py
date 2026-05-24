#!/usr/bin/env python3
import sys
import asyncio
from telethon import TelegramClient
from config import API_ID, API_HASH, PHONE_NUMBER, SESSION_DIR

async def quick_auth():
    client = TelegramClient(str(SESSION_DIR / "user"), API_ID, API_HASH)
    code = sys.argv[1] if len(sys.argv) > 1 else input("Code: ")
    await client.start(phone=PHONE_NUMBER, code_callback=lambda: code)
    me = await client.get_me()
    print(f"✓ Authorized as {me.first_name} ({me.phone})")
    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(quick_auth())
