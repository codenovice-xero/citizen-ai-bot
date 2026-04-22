import logging
import discord
from discord.ext import commands

from .config import settings
from .services import StarCitizenService


class CitizenAIBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(command_prefix="!", intents=intents)
        self.service = StarCitizenService()

    async def setup_hook(self):
        await self.load_extension("citizen_ai_bot.cogs.starcitizen")

        if settings.discord_guild_id:
            guild = discord.Object(id=settings.discord_guild_id)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()

    async def close(self):
        await self.service.close()
        await super().close()


def run():
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )

    if not settings.discord_token:
        raise RuntimeError("DISCORD_TOKEN missing")

    bot = CitizenAIBot()
    bot.run(settings.discord_token)
