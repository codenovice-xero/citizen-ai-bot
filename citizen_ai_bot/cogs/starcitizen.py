from __future__ import annotations

import asyncio
import logging

import discord
from discord import app_commands
from discord.ext import commands

from ..config import settings
from ..formatters import (
    error_embed,
    format_advice,
    format_item_result,
    format_loadout,
    format_mining,
    format_risk,
    format_route,
    format_route_list,
    format_trend,
    help_embed,
    status_embed,
)
from ..services import StarCitizenService
from ..uex_client import UEXClient

log = logging.getLogger(__name__)


class StarCitizenCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.client = UEXClient()
        self.service = StarCitizenService(self.client)

    async def cog_unload(self) -> None:
        await self.client.close()

    @app_commands.command(name="item", description="Find where an in-game item can be bought or sold")
    async def item(self, interaction: discord.Interaction, name: str) -> None:
        await interaction.response.defer(thinking=True)
        try:
            matches, locations = await asyncio.wait_for(self.service.get_item_locations(name), timeout=20)
            await interaction.followup.send(embed=format_item_result(matches, locations))
        except Exception as exc:
            log.exception("item command failed")
            await interaction.followup.send(embed=error_embed("Item Lookup Failed", str(exc)))

    @app_commands.command(name="route", description="Find the best current route for a commodity")
    async def route(
        self,
        interaction: discord.Interaction,
        commodity: str,
        from_location: str | None = None,
        budget: float | None = None,
        scu: float | None = None,
        legal_only: bool = False,
    ) -> None:
        await interaction.response.defer(thinking=True)
        try:
            route = await asyncio.wait_for(
                self.service.suggest_trade_route(
                    commodity_name=commodity,
                    from_location=from_location,
                    budget=budget,
                    cargo_scu=scu,
                    legal_only=legal_only,
                ),
                timeout=20,
            )
            if not route:
                await interaction.followup.send(
                    embed=error_embed("No Route Found", "No route matched that commodity and filter set.")
                )
                return
            await interaction.followup.send(embed=format_route(route))
        except Exception as exc:
            log.exception("route command failed")
            await interaction.followup.send(embed=error_embed("Route Lookup Failed", str(exc)))

    @app_commands.command(name="multiroute", description="Show several route options for a commodity")
    async def multiroute(
        self,
        interaction: discord.Interaction,
        commodity: str,
        from_location: str | None = None,
        budget: float | None = None,
        scu: float | None = None,
        legal_only: bool = False,
    ) -> None:
        await interaction.response.defer(thinking=True)
        try:
            routes = await asyncio.wait_for(
                self.service.list_trade_routes(
                    commodity_name=commodity,
                    from_location=from_location,
                    budget=budget,
                    cargo_scu=scu,
                    legal_only=legal_only,
                    limit=5,
                ),
                timeout=20,
            )
            await interaction.followup.send(embed=format_route_list(routes))
        except Exception as exc:
            log.exception("multiroute failed")
            await interaction.followup.send(embed=error_embed("Multi-Route Lookup Failed", str(exc)))

    @app_commands.command(name="advice", description="Get money-making guidance based on your ship and bankroll")
    async def advice(
        self,
        interaction: discord.Interaction,
        money: float | None = None,
        ship: str | None = None,
        risk_tolerance: str | None = None,
    ) -> None:
        plan = self.service.advice_for_player(money=money, ship=ship, risk_tolerance=risk_tolerance)
        await interaction.response.send_message(embed=format_advice(plan))

    @app_commands.command(name="loadout", description="Show a curated loadout recommendation for a ship")
    async def loadout(self, interaction: discord.Interaction, ship: str) -> None:
        suggestion = self.service.suggest_loadout(ship)
        await interaction.response.send_message(embed=format_loadout(suggestion, ship))

    @app_commands.command(name="mining", description="Show a curated mining plan for a mining ship")
    async def mining(self, interaction: discord.Interaction, ship: str) -> None:
        suggestion = self.service.suggest_mining(ship)
        await interaction.response.send_message(embed=format_mining(suggestion, ship))

    @app_commands.command(name="missions", description="Show mission progression advice")
    async def missions(self, interaction: discord.Interaction, mission_type: str) -> None:
        plan = self.service.mission_plan(mission_type)
        await interaction.response.send_message(embed=format_advice(plan))

    @app_commands.command(name="risk", description="Estimate route risk between two locations")
    async def risk(self, interaction: discord.Interaction, buy_location: str, sell_location: str, legal_only: bool = False) -> None:
        label, notes = self.service.estimate_route_risk(buy_location, sell_location, legal_only=legal_only)
        await interaction.response.send_message(embed=format_risk(label, notes))

    @app_commands.command(name="trend", description="Show a current-market snapshot for a commodity")
    async def trend(self, interaction: discord.Interaction, commodity: str) -> None:
        await interaction.response.defer(thinking=True)
        try:
            snapshot = await asyncio.wait_for(self.service.price_snapshot(commodity), timeout=20)
            if not snapshot:
                await interaction.followup.send(embed=error_embed("No Snapshot Found", "No commodity snapshot matched that query."))
                return
            await interaction.followup.send(embed=format_trend(snapshot))
        except Exception as exc:
            log.exception("trend failed")
            await interaction.followup.send(embed=error_embed("Trend Lookup Failed", str(exc)))

    @app_commands.command(name="op", description="Generate a simple org-op checklist")
    async def op(self, interaction: discord.Interaction, event: str) -> None:
        plan = self.service.plan_operation(event)
        await interaction.response.send_message(embed=format_advice(plan))

    @app_commands.command(name="status", description="Check API and bot health")
    async def status(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(thinking=True)
        healthy = await self.client.ping()
        await interaction.followup.send(embed=status_embed(healthy))

    @app_commands.command(name="helpme", description="Show quick command help")
    async def helpme(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(embed=help_embed())


async def setup(bot: commands.Bot) -> None:
    cog = StarCitizenCog(bot)
    await bot.add_cog(cog, guild=discord.Object(id=settings.discord_guild_id) if settings.discord_guild_id else None)
