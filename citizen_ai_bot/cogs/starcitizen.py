from __future__ import annotations

import asyncio
import logging

import discord
from discord import app_commands
from discord.ext import commands

from ..formatters import commodity_embed, item_embed, route_embed, status_embed
from ..services import StarCitizenService

log = logging.getLogger(__name__)


class StarCitizenCog(commands.Cog):
    def __init__(self, bot: commands.Bot, service: StarCitizenService) -> None:
        self.bot = bot
        self.service = service

    @app_commands.command(name="helpme", description="Show Citizen AI command help.")
    async def helpme(self, interaction: discord.Interaction) -> None:
        embed = discord.Embed(title="Citizen AI • Commands")
        embed.add_field(name="/item", value="Find likely shop locations for an item.", inline=False)
        embed.add_field(name="/commodity", value="Find matching commodities.", inline=False)
        embed.add_field(name="/route", value="Generate a starter trade route suggestion.", inline=False)
        embed.add_field(name="/status", value="Check bot and API status.", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="status", description="Check bot and API status.")
    async def status(self, interaction: discord.Interaction) -> None:
        ok = await self.service.client.ping()
        await interaction.response.send_message(embed=status_embed(ok), ephemeral=True)

    @app_commands.command(name="item", description="Find likely buy locations for an item.")
    @app_commands.describe(name="Item or component name, e.g. Atlas, Omnisky, Rieger")
    async def item(self, interaction: discord.Interaction, name: str) -> None:
        await interaction.response.defer(thinking=True)
        matches, locations = await self.service.get_item_locations(name)
        await interaction.followup.send(embed=item_embed(name, matches, locations))

    @app_commands.command(name="commodity", description="Search for a commodity.")
    @app_commands.describe(name="Commodity name, e.g. Gold, Agricium, Quantanium")
    async def commodity(self, interaction: discord.Interaction, name: str) -> None:
        await interaction.response.defer(thinking=True)
        matches = await self.service.search_commodity(name)
        await interaction.followup.send(embed=commodity_embed(name, matches))

    @app_commands.command(name="route", description="Suggest a starter trade route for a commodity.")
    @app_commands.describe(
        commodity="Commodity name, e.g. Gold",
        from_location="Optional starting terminal or area",
        budget="Optional budget in aUEC",
        cargo_scu="Optional cargo size in SCU",
    )
    async def route(
        self,
        interaction: discord.Interaction,
        commodity: str,
        from_location: str | None = None,
        budget: float | None = None,
        cargo_scu: float | None = None,
    ) -> None:
        await interaction.response.defer(thinking=True)
        try:
            route = await asyncio.wait_for(
                self.service.suggest_trade_route(
                    commodity_name=commodity,
                    from_location=from_location,
                    budget=budget,
                    cargo_scu=cargo_scu,
                ),
                timeout=20,
            )
        except asyncio.TimeoutError:
            await interaction.followup.send(
                "Route search timed out while waiting on live market data. Please try again in a moment."
            )
            return
        except Exception as exc:
            log.exception("Route command failed for commodity=%s", commodity)
            await interaction.followup.send(
                f"Route lookup failed for **{commodity}**: `{type(exc).__name__}`."
            )
            return

        if route is None:
            await interaction.followup.send(
                f"I couldn't find a route suggestion for **{commodity}** with the current live data."
            )
            return
        await interaction.followup.send(embed=route_embed(route, budget=budget, cargo_scu=cargo_scu))


async def setup(bot: commands.Bot) -> None:
    service = bot.star_service  # type: ignore[attr-defined]
    await bot.add_cog(StarCitizenCog(bot, service))
