from __future__ import annotations

import asyncio
import logging

from .bot import CitizenAIBot
from .config import settings


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)


async def main() -> None:
    if not settings.discord_token.strip():
        raise RuntimeError("DISCORD_TOKEN is missing. Copy .env.example to .env and fill it in.")

    bot = CitizenAIBot()
    async with bot:
        await bot.start(settings.discord_token)


if __name__ == "__main__":
    asyncio.run(main())
