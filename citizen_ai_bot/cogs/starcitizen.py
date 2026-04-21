from __future__ import annotations

import asyncio

import discord
from discord.ext import commands

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


class StarCitizenCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.service = getattr(bot, "sc_service", None) or getattr(bot, "service", None)

    @discord.app_commands.command(name="helpme", description="Show Citizen AI commands")
    async def helpme(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(embed=help_embed())

    @discord.app_commands.command(name="status", description="Check bot, UEX, and Wiki API status")
    async def status(self, interaction: discord.Interaction) -> None:
        status = {"uex": False, "wiki": False}
        try:
            if self.service:
                status = await self.service.health_status()
        except Exception:
            status = {"uex": False, "wiki": False}
        await interaction.response.send_message(embed=status_embed(status))

    @discord.app_commands.command(name="item", description="Find where an item can be bought or sold")
    async def item(self, interaction: discord.Interaction, name: str) -> None:
        await interaction.response.defer(thinking=True)
        try:
            matches, locations = await self.service.get_item_locations(name)
            await interaction.followup.send(embed=format_item_result(matches, locations))
        except Exception as exc:
            await interaction.followup.send(embed=error_embed("Item Lookup Failed", str(exc)))

    @discord.app_commands.command(name="route", description="Find the best trade route for a commodity")
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
                await interaction.followup.send(embed=error_embed("Route Lookup", "No route found for that query."))
                return
            await interaction.followup.send(embed=format_route(route))
        except Exception as exc:
            await interaction.followup.send(embed=error_embed("Route Lookup Failed", str(exc)))

    @discord.app_commands.command(name="multiroute", description="Show multiple good trade routes")
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
            await interaction.followup.send(embed=error_embed("Multi-Route Lookup Failed", str(exc)))

    @discord.app_commands.command(name="advice", description="Get activity advice based on money, ship, and risk tolerance")
    async def advice(
        self,
        interaction: discord.Interaction,
        money: float | None = None,
        ship: str | None = None,
        risk_tolerance: str | None = None,
    ) -> None:
        try:
            plan = self.service.advice_for_player(money, ship, risk_tolerance)
            await interaction.response.send_message(embed=format_advice(plan))
        except Exception as exc:
            await interaction.response.send_message(embed=error_embed("Advice Failed", str(exc)))

    @discord.app_commands.command(name="loadout", description="Get a recommended ship loadout")
    async def loadout(self, interaction: discord.Interaction, ship: str) -> None:
        await interaction.response.defer(thinking=True)
        try:
            loadout = await self.service.suggest_loadout(ship)
            await interaction.followup.send(embed=format_loadout(loadout, ship))
        except Exception as exc:
            await interaction.followup.send(embed=error_embed("Loadout Failed", str(exc)))

    @discord.app_commands.command(name="mining", description="Get a mining setup recommendation")
    async def mining(self, interaction: discord.Interaction, ship: str) -> None:
        try:
            plan = self.service.suggest_mining(ship)
            await interaction.response.send_message(embed=format_mining(plan, ship))
        except Exception as exc:
            await interaction.response.send_message(embed=error_embed("Mining Failed", str(exc)))

    @discord.app_commands.command(name="missions", description="Get mission-path guidance")
    async def missions(self, interaction: discord.Interaction, mission_type: str) -> None:
        try:
            plan = self.service.mission_plan(mission_type)
            await interaction.response.send_message(embed=format_advice(plan))
        except Exception as exc:
            await interaction.response.send_message(embed=error_embed("Mission Guidance Failed", str(exc)))

    @discord.app_commands.command(name="risk", description="Estimate route risk between two places")
    async def risk(self, interaction: discord.Interaction, buy_location: str, sell_location: str, legal_only: bool = False) -> None:
        try:
            label, notes = self.service.estimate_route_risk(buy_location, sell_location, legal_only=legal_only)
            await interaction.response.send_message(embed=format_risk(label, notes))
        except Exception as exc:
            await interaction.response.send_message(embed=error_embed("Risk Failed", str(exc)))

    @discord.app_commands.command(name="trend", description="Show a current commodity market snapshot")
    async def trend(self, interaction: discord.Interaction, commodity: str) -> None:
        await interaction.response.defer(thinking=True)
        try:
            snapshot = await self.service.price_snapshot(commodity)
            if not snapshot:
                await interaction.followup.send(embed=error_embed("Snapshot Lookup", "No market snapshot found for that commodity."))
                return
            await interaction.followup.send(embed=format_trend(snapshot))
        except Exception as exc:
            await interaction.followup.send(embed=error_embed("Snapshot Failed", str(exc)))

    @discord.app_commands.command(name="op", description="Create a simple org operation checklist")
    async def op(self, interaction: discord.Interaction, event: str) -> None:
        try:
            plan = self.service.plan_operation(event)
            await interaction.response.send_message(embed=format_advice(plan))
        except Exception as exc:
            await interaction.response.send_message(embed=error_embed("Operation Planner Failed", str(exc)))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(StarCitizenCog(bot))
