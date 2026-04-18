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
        self.uex_client = UEXClient()
        self.star_service = StarCitizenService(self.uex_client)

    async def setup_hook(self) -> None:
        await self.load_extension("citizen_ai_bot.cogs.starcitizen")
        if settings.guild_id_int:
            guild = discord.Object(id=settings.guild_id_int)
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            log.info("Synced %s guild commands", len(synced))
        else:
            synced = await self.tree.sync()
            log.info("Synced %s global commands", len(synced))

    async def close(self) -> None:
        await self.uex_client.close()
        await super().close()


async def create_bot() -> CitizenAIBot:
    return CitizenAIBot()
