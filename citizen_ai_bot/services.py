from __future__ import annotations

import logging
from typing import Any

from .wiki_client import WikiClient

log = logging.getLogger(__name__)


class StarCitizenService:
    """
    Primary service layer for Citizen AI.

    This version keeps legacy attribute names (`client`, `wiki`) so the
    existing bot/cogs continue working, while routing /loadout through the
    new wiki-first pipeline.
    """

    def __init__(self, client: Any | None = None) -> None:
        # Preserve old `client` attribute if other commands still expect it.
        self.client = client
        self.wiki = WikiClient()

    async def close(self) -> None:
        """Close outbound HTTP clients."""
        try:
            if self.client and hasattr(self.client, "close"):
                maybe = self.client.close()
                if hasattr(maybe, "__await__"):
                    await maybe
        except Exception:
            log.exception("Failed closing primary client")

        try:
            await self.wiki.close()
        except Exception:
            log.exception("Failed closing wiki client")

    async def health(self) -> dict[str, bool]:
        """Health probe for /status command."""
        api_ok = False
        wiki_ok = False

        if self.client and hasattr(self.client, "ping"):
            try:
                maybe = self.client.ping()
                api_ok = await maybe if hasattr(maybe, "__await__") else bool(maybe)
            except Exception:
                api_ok = False

        try:
            wiki_ok = await self.wiki.ping()
        except Exception:
            wiki_ok = False

        return {
            "primary_api": api_ok,
            "wiki_api": wiki_ok,
            "overall": api_ok or wiki_ok,
        }

    async def suggest_loadout(self, ship_name: str):
        """
        Legacy-compatible entrypoint used by existing /loadout command.
        Returns LoadoutReport from the new wiki pipeline.
        """
        return await self.wiki.build_loadout_report(ship_name)

    async def build_loadout_report(self, ship_name: str):
        """Explicit new entrypoint."""
        return await self.wiki.build_loadout_report(ship_name)

    async def get_hardpoints(self, ship_name: str):
        return await self.wiki.get_hardpoints(ship_name)

    async def get_performance(self, ship_name: str):
        return await self.wiki.get_performance(ship_name)

    async def advice_for_player(
        self,
        money: int | None = None,
        ship: str | None = None,
        risk_tolerance: str | None = None,
    ) -> str:
        """
        Lightweight placeholder that still respects risk_tolerance.
        Keeps /advice command functional.
        """
        profile = (risk_tolerance or "medium").lower()

        if profile == "low":
            focus = "safe contracts, hauling, legal bounties, steady progression"
        elif profile == "high":
            focus = "high-risk combat, salvage races, PvP zones, speculative cargo"
        else:
            focus = "mixed contracts, bounty chains, trading, upgrade planning"

        parts = ["Recommended focus: " + focus]
        if money is not None:
            parts.append(f"Budget: {money:,} aUEC")
        if ship:
            parts.append(f"Current ship: {ship}")

        return " | ".join(parts)
