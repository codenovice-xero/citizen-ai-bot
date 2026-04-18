from __future__ import annotations

import asyncio
import logging

import discord
from discord import app_commands
from discord.ext import commands

from ..config import settings
from ..formatters import (
    format_advice,
    format_item_result,
    format_loadout,
    format_mining,
    format_route,
    format_route_list,
)
from ..services import StarCitizenService
from ..uex_client import UEXClient
from ..utils import fmt_credits

log = logging.getLogger(__name__)


class StarCitizenCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.client = UEXClient()
        self.service = StarCitizenService(self.client)

    async def cog_unload(self) -> None:
        await self.client.close()

    def _guild(self) -> discord.Object | None:
        return discord.Object(id=settings.discord_guild_id) if settings.discord_guild_id else None

    @app_commands.command(name="item", description="Find where an in-game item can be bought or sold")
    async def item(self, interaction: discord.Interaction, name: str) -> None:
        await interaction.response.defer(thinking=True)
        try:
            matches, locations = await asyncio.wait_for(self.service.get_item_locations(name), timeout=20)
            await interaction.followup.send(format_item_result(matches, locations))
        except Exception as exc:
            log.exception("item command failed")
            await interaction.followup.send(f"Item lookup failed: {exc}")

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
                await interaction.followup.send("No route found for that commodity and filter set.")
                return
            await interaction.followup.send(format_route(route))
        except Exception as exc:
            log.exception("route command failed")
            await interaction.followup.send(f"Route lookup failed: {exc}")

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
            await interaction.followup.send(format_route_list(routes))
        except Exception as exc:
            log.exception("multiroute failed")
            await interaction.followup.send(f"Multi-route lookup failed: {exc}")

    @app_commands.command(name="advice", description="Get money-making guidance based on your ship and bankroll")
    async def advice(
        self,
        interaction: discord.Interaction,
        money: float | None = None,
        ship: str | None = None,
        risk_tolerance: str | None = None,
    ) -> None:
        plan = self.service.advice_for_player(money=money, ship=ship, risk_tolerance=risk_tolerance)
        await interaction.response.send_message(format_advice(plan))

    @app_commands.command(name="loadout", description="Show a curated loadout recommendation for a ship")
    async def loadout(self, interaction: discord.Interaction, ship: str) -> None:
        suggestion = self.service.suggest_loadout(ship)
        await interaction.response.send_message(format_loadout(suggestion, ship))

    @app_commands.command(name="mining", description="Show a curated mining plan for a mining ship")
    async def mining(self, interaction: discord.Interaction, ship: str) -> None:
        suggestion = self.service.suggest_mining(ship)
        await interaction.response.send_message(format_mining(suggestion, ship))

    @app_commands.command(name="missions", description="Show mission progression advice")
    async def missions(self, interaction: discord.Interaction, mission_type: str) -> None:
        plan = self.service.mission_plan(mission_type)
        await interaction.response.send_message(format_advice(plan))

    @app_commands.command(name="risk", description="Estimate route risk between two locations")
    async def risk(self, interaction: discord.Interaction, buy_location: str, sell_location: str, legal_only: bool = False) -> None:
        label, notes = self.service.estimate_route_risk(buy_location, sell_location, legal_only=legal_only)
        message = [f"**Risk: {label}**"]
        message.extend(f"• {note}" for note in notes)
        await interaction.response.send_message("\n".join(message))

    @app_commands.command(name="trend", description="Show a current-market snapshot for a commodity")
    async def trend(self, interaction: discord.Interaction, commodity: str) -> None:
        await interaction.response.defer(thinking=True)
        try:
            snapshot = await asyncio.wait_for(self.service.price_snapshot(commodity), timeout=20)
            if not snapshot:
                await interaction.followup.send("No commodity snapshot found for that query.")
                return
            route = snapshot["top_route"]
            message = (
                f"**{snapshot['commodity']} snapshot**\n"
                f"Best margin seen: {fmt_credits(snapshot['best_margin'])}\n"
                f"Average top-route margin: {fmt_credits(snapshot['avg_margin'])}\n"
                f"Top current route: {route.buy_location} -> {route.sell_location}\n"
                f"{snapshot['trend_note']}"
            )
            await interaction.followup.send(message)
        except Exception as exc:
            log.exception("trend failed")
            await interaction.followup.send(f"Trend lookup failed: {exc}")

    @app_commands.command(name="op", description="Generate a simple org-op checklist")
    async def op(self, interaction: discord.Interaction, event: str) -> None:
        plan = self.service.plan_operation(event)
        await interaction.response.send_message(format_advice(plan))

    @app_commands.command(name="status", description="Check API and bot health")
    async def status(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(thinking=True)
        healthy = await self.client.ping()
        message = "Citizen AI is online. UEX API reachable." if healthy else "Citizen AI is online, but UEX did not answer the health check."
        await interaction.followup.send(message)

    @app_commands.command(name="helpme", description="Show quick command help")
    async def helpme(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(
            "\n".join(
                [
                    "**Citizen AI commands**",
                    "/item name:<item>",
                    "/route commodity:<commodity> [from_location] [budget] [scu] [legal_only]",
                    "/multiroute commodity:<commodity> [from_location] [budget] [scu] [legal_only]",
                    "/advice [money] [ship] [risk_tolerance]",
                    "/loadout ship:<ship>",
                    "/mining ship:<ship>",
                    "/missions mission_type:<type>",
                    "/risk buy_location:<place> sell_location:<place>",
                    "/trend commodity:<commodity>",
                    "/op event:<name>",
                    "/status",
                ]
            )
        )


async def setup(bot: commands.Bot) -> None:
    cog = StarCitizenCog(bot)
    await bot.add_cog(cog, guild=discord.Object(id=settings.discord_guild_id) if settings.discord_guild_id else None)
