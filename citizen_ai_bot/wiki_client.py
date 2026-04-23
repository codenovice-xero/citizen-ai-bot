from __future__ import annotations

import logging
from typing import Any

import httpx

from .config import settings
from .loadout_engine import LoadoutEngine
from .models import LoadoutReport

log = logging.getLogger(__name__)


class WikiClient:
    """
    Loadout v3:
    - Uses internal ship/component data as the authority for role-based builds.
    - Keeps Wiki API health check / future enrichment surface.
    - Avoids fragile recursive vehicle-port parsing for build recommendations.
    """

    def __init__(self, timeout: float = 20.0) -> None:
        self._http = httpx.AsyncClient(
            base_url=settings.wiki_api_base.rstrip("/"),
            timeout=timeout,
            follow_redirects=True,
            headers={"Accept": "application/json", "User-Agent": "CitizenAI-DiscordBot/1.0"},
        )
        self.engine = LoadoutEngine()

    async def close(self) -> None:
        await self._http.aclose()

    async def ping(self) -> bool:
        for path in ("/api/vehicles/Gladius", "/api/v3/vehicles/Gladius", "/"):
            try:
                response = await self._http.get(path)
                response.raise_for_status()
                return True
            except Exception:
                continue
        return False

    async def build_loadout_report(
        self,
        ship_name: str,
        requested_role: str | None = None,
    ) -> LoadoutReport | None:
        return self.engine.build(ship_name, requested_role)

    # Kept for compatibility with existing service code that may still call get_ship.
    async def get_ship(self, ship_name: str) -> dict[str, Any] | None:
        key = self.engine.resolve_ship_key(ship_name)
        if not key:
            return None
        return self.engine.ship_db.get(key)
