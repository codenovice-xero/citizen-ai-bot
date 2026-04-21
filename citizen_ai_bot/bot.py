from __future__ import annotations

import logging

import discord
from discord.ext import commands

from .config import settings
from .services import StarCitizenService
from .uex_client import UEXClient

log = logging.getLogger(__name__)


class CitizenAIBot(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        super().__init__(command_prefix="!", intents=intents)
        self.service = StarCitizenService(UEXClient(api_token=settings.uex_api_token))
        self.sc_service = self.service

    async def setup_hook(self) -> None:
        await self.load_extension("citizen_ai_bot.cogs.starcitizen")
        if settings.discord_guild_id:
            guild = discord.Object(id=settings.discord_guild_id)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            log.info("Synced application commands to guild %s", settings.discord_guild_id)
        else:
            await self.tree.sync()
            log.info("Synced global application commands")

    async def close(self) -> None:
        try:
            await self.service.close()
        finally:
            await super().close()
