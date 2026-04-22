from __future__ import annotations

import logging
from typing import Any

from .uex_client import UEXClient
from .wiki_client import WikiClient

log = logging.getLogger(__name__)


class StarCitizenService:
    def __init__(self) -> None:
        self.client = UEXClient()
        self.wiki = WikiClient()

    async def close(self) -> None:
        try:
            await self.client.close()
        except Exception:
            log.exception("Failed closing UEX client")

        try:
            await self.wiki.close()
        except Exception:
            log.exception("Failed closing Wiki client")

    async def health_status(self) -> dict[str, bool]:
        uex_ok = False
        wiki_ok = False

        try:
            uex_ok = await self.client.ping()
        except Exception:
            uex_ok = False

        try:
            wiki_ok = await self.wiki.ping()
        except Exception:
            wiki_ok = False

        return {
            "uex_api": uex_ok,
            "wiki_api": wiki_ok,
            "overall": uex_ok or wiki_ok,
        }

    async def get_item_locations(self, name: str, location: str | None = None) -> list[dict[str, Any]]:
        return await self.client.get_item_locations(name, location=location)

    async def suggest_trade_route(self, commodity: str) -> str:
        rows = await self.client.price_snapshot(commodity)
        if not rows:
            return f"No live market snapshot was returned for {commodity}."
        return f"Live market snapshot found {len(rows)} rows for {commodity}. Use /trend for pricing context."

    async def list_trade_routes(self, commodity: str) -> str:
        return await self.suggest_trade_route(commodity)

    async def advice_for_player(
        self,
        money: int | None = None,
        ship: str | None = None,
        risk_tolerance: str | None = None,
    ) -> str:
        profile = (risk_tolerance or "medium").lower()

        if profile == "low":
            focus = "safe contracts, hauling, legal bounties, steady progression"
        elif profile == "high":
            focus = "high-risk combat, salvage races, PvP zones, speculative cargo"
        else:
            focus = "mixed contracts, bounty chains, trading, upgrade planning"

        parts = [f"Recommended focus: {focus}"]
        if money is not None:
            parts.append(f"Budget: {money:,} aUEC")
        if ship:
            parts.append(f"Current ship: {ship}")

        return " | ".join(parts)

    async def suggest_loadout(self, ship_name: str):
        return await self.wiki.build_loadout_report(ship_name)

    async def suggest_mining(self, ship_name: str | None = None) -> str:
        return (
            f"Mining recommendation: use a stable laser/module mix for your {ship_name or 'ship'} "
            f"and prioritize controllable rocks."
        )

    async def mission_plan(self, ship_name: str | None = None, activity: str | None = None) -> str:
        return (
            f"Mission plan: bring medpens, tractor support, spare ammo, and set respawn before "
            f"running {activity or 'contracts'} in your {ship_name or 'ship'}."
        )

    async def estimate_route_risk(self, start: str | None = None, end: str | None = None) -> str:
        return (
            f"Route risk between {start or 'origin'} and {end or 'destination'} is situational. "
            f"Check traffic, PvP hotspots, and armistice coverage."
        )

    async def price_snapshot(self, commodity: str) -> str:
        rows = await self.client.price_snapshot(commodity)
        if not rows:
            return f"No live market snapshot was returned for {commodity}."
        return f"Live market snapshot: {len(rows)} rows returned for {commodity}. This is not historical trend analysis."

    async def plan_operation(self, ship_name: str | None = None, objective: str | None = None) -> str:
        return (
            f"Operation plan: stage at a safe medical/cargo hub, set rally point, assign escort, "
            f"then execute {objective or 'objective'} with {ship_name or 'available ships'}."
        )
