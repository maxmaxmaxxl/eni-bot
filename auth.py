#!/usr/bin/env python3
import asyncio
import sys
import os
import time
from pathlib import Path
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError
from config import API_ID, API_HASH, PHONE_NUMBER, SESSION_DIR

CODE_FILE = Path("/tmp/eni_auth_code.txt")

async def main():
    session_file = str(SESSION_DIR / "user")
    for f in [session_file, session_file + "-journal"]:
        if os.path.exists(f):
            os.remove(f)

    client = TelegramClient(session_file, API_ID, API_HASH)
    await client.connect()

    if await client.is_user_authorized():
        print("Already authorized")
        await client.disconnect()
        return

    await client.send_code_request(PHONE_NUMBER)
    print("CODE_SENT")
    sys.stdout.flush()

    # Wait for code file to appear (up to 120s)
    code = None
    for _ in range(120):
        if CODE_FILE.exists():
            code = CODE_FILE.read_text().strip()
            if code:
                break
        await asyncio.sleep(1)

    if not code:
        print("NO_CODE_TIMEOUT")
        await client.disconnect()
        return

    try:
        await client.sign_in(phone=PHONE_NUMBER, code=code)
    except SessionPasswordNeededError:
        print("PASSWORD_REQUIRED")
        sys.stdout.flush()
        pwd = None
        pwd_file = Path("/tmp/eni_auth_password.txt")
        for _ in range(120):
            if pwd_file.exists():
                pwd = pwd_file.read_text().strip()
                if pwd:
                    break
            await asyncio.sleep(1)

        if not pwd:
            print("NO_PASSWORD_TIMEOUT")
            await client.disconnect()
            return
        await client.sign_in(password=pwd)

    if await client.is_user_authorized():
        me = await client.get_me()
        print(f"AUTH_OK:{me.id}:{me.first_name}")
    else:
        print("AUTH_FAILED")

    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
