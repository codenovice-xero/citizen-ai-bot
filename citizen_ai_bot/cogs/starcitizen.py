from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from ..formatters import item_embed, loadout_embed, simple_embed, status_embed


class StarCitizenCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.service = bot.service

    @app_commands.command(name="helpme", description="Show command help.")
    async def helpme(self, interaction: discord.Interaction) -> None:
        text = "/status, /item, /route, /multiroute, /advice, /loadout, /mining, /missions, /risk, /trend, /op"
        await interaction.response.send_message(embed=simple_embed("Citizen AI Help", text))

    @app_commands.command(name="status", description="Check bot and provider health.")
    async def status(self, interaction: discord.Interaction) -> None:
        status = await self.service.health_status()
        await interaction.response.send_message(embed=status_embed(status))

    @app_commands.command(name="item", description="Find item sale / buy data.")
    async def item(
        self,
        interaction: discord.Interaction,
        name: str,
        location: str | None = None,
    ) -> None:
        await interaction.response.defer()
        rows = await self.service.get_item_locations(name, location=location)
        resolved_location = rows[0].get("_resolved_location") if rows else None
        await interaction.followup.send(embed=item_embed(name, rows, location=location, resolved_location=resolved_location))

    @app_commands.command(name="route", description="Quick trade route guidance.")
    async def route(self, interaction: discord.Interaction, commodity: str) -> None:
        text = await self.service.suggest_trade_route(commodity)
        await interaction.response.send_message(embed=simple_embed(f"Route • {commodity}", text))

    @app_commands.command(name="multiroute", description="Multi-stop trade route guidance.")
    async def multiroute(self, interaction: discord.Interaction, commodity: str) -> None:
        text = await self.service.list_trade_routes(commodity)
        await interaction.response.send_message(embed=simple_embed(f"Multi-route • {commodity}", text))

    @app_commands.command(name="advice", description="General progression advice.")
    async def advice(
        self,
        interaction: discord.Interaction,
        money: int | None = None,
        ship: str | None = None,
        risk_tolerance: str | None = None,
    ) -> None:
        text = await self.service.advice_for_player(
            money=money,
            ship=ship,
            risk_tolerance=risk_tolerance,
        )
        await interaction.response.send_message(embed=simple_embed("Advice", text))

    @app_commands.command(name="loadout", description="Ship loadout recommendation and mounted component report.")
    async def loadout(self, interaction: discord.Interaction, ship_name: str) -> None:
        report = await self.service.suggest_loadout(ship_name)
        await interaction.response.send_message(embed=loadout_embed(report, ship_name))

    @app_commands.command(name="mining", description="Mining suggestion.")
    async def mining(self, interaction: discord.Interaction, ship_name: str | None = None) -> None:
        text = await self.service.suggest_mining(ship_name)
        await interaction.response.send_message(embed=simple_embed("Mining", text))

    @app_commands.command(name="missions", description="Mission plan.")
    async def missions(
        self,
        interaction: discord.Interaction,
        ship_name: str | None = None,
        activity: str | None = None,
    ) -> None:
        text = await self.service.mission_plan(ship_name, activity)
        await interaction.response.send_message(embed=simple_embed("Missions", text))

    @app_commands.command(name="risk", description="Estimate route risk.")
    async def risk(
        self,
        interaction: discord.Interaction,
        start: str | None = None,
        end: str | None = None,
    ) -> None:
        text = await self.service.estimate_route_risk(start, end)
        await interaction.response.send_message(embed=simple_embed("Risk", text))

    @app_commands.command(name="trend", description="Show a live market snapshot.")
    async def trend(self, interaction: discord.Interaction, commodity: str) -> None:
        text = await self.service.price_snapshot(commodity)
        await interaction.response.send_message(embed=simple_embed(f"Trend • {commodity}", text))

    @app_commands.command(name="op", description="Plan an operation.")
    async def op(
        self,
        interaction: discord.Interaction,
        ship_name: str | None = None,
        objective: str | None = None,
    ) -> None:
        text = await self.service.plan_operation(ship_name, objective)
        await interaction.response.send_message(embed=simple_embed("Operation", text))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(StarCitizenCog(bot))
