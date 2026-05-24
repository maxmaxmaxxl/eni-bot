#!/usr/bin/env python3
import asyncio
import sys

from bot import AssistantBot


async def main():
    bot = AssistantBot()
    try:
        await bot.start()
    except KeyboardInterrupt:
        print("\nShutting down...")
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
