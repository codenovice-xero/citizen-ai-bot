from __future__ import annotations

import logging

import discord
from discord.ext import commands

from .config import settings
from .services import StarCitizenService
from .uex_client import UEXClient
from .wiki_client import WikiClient

log = logging.getLogger(__name__)


class CitizenAIBot(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        super().__init__(command_prefix="!", intents=intents)
        self.wiki_client = WikiClient()
        self.sc_service = StarCitizenService(UEXClient(), wiki=self.wiki_client)

    async def setup_hook(self) -> None:
        await self.load_extension("citizen_ai_bot.cogs.starcitizen")
        if settings.discord_guild_id:
            guild = discord.Object(id=settings.discord_guild_id)
            synced = await self.tree.sync(guild=guild)
            log.info("Synced %s guild commands", len(synced))
        else:
            synced = await self.tree.sync()
            log.info("Synced %s global commands", len(synced))

    async def close(self) -> None:
        try:
            await self.sc_service.client.close()
            await self.wiki_client.close()
        finally:
            await super().close()

    async def on_ready(self) -> None:
        log.info("Bot connected as %s", self.user)
