from __future__ import annotations

import logging

import discord
from discord.ext import commands

from .config import settings

log = logging.getLogger(__name__)


class CitizenAIBot(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self) -> None:
        await self.load_extension("citizen_ai_bot.cogs.starcitizen")
        if settings.discord_guild_id:
            guild = discord.Object(id=settings.discord_guild_id)
            synced = await self.tree.sync(guild=guild)
            log.info("Synced %s guild commands", len(synced))
        else:
            synced = await self.tree.sync()
            log.info("Synced %s global commands", len(synced))

    async def on_ready(self) -> None:
        log.info("Bot connected as %s", self.user)
