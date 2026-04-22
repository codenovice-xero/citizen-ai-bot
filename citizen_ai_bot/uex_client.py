from __future__ import annotations

import logging
from typing import Any

import httpx

from .config import settings

log = logging.getLogger(__name__)


class UEXClient:
    def __init__(self) -> None:
        headers = {
            "Accept": "application/json",
            "User-Agent": "CitizenAI-DiscordBot/1.0",
        }
        if settings.uex_api_token:
            headers["Authorization"] = f"Bearer {settings.uex_api_token}"

        self._http = httpx.AsyncClient(
            base_url=settings.uex_api_base.rstrip("/"),
            timeout=20.0,
            follow_redirects=True,
            headers=headers,
        )

    async def close(self) -> None:
        await self._http.aclose()

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        response = await self._http.get(path, params=params)
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, dict) and "data" in payload:
            return payload["data"]
        return payload

    async def ping(self) -> bool:
        for path in ("/commodities_prices", "/items", "/star_systems"):
            try:
                data = await self._get(path, params={"limit": 1})
                if data is not None:
                    return True
            except Exception as exc:
                log.debug("UEX ping failed on %s: %s", path, exc)
        return False

    async def get_item_locations(self, name: str) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []

        for path in ("/items_prices", "/items"):
            try:
                data = await self._get(path, params={"search": name, "limit": 100})
                if isinstance(data, list):
                    rows.extend(x for x in data if isinstance(x, dict))
            except Exception as exc:
                log.debug("UEX item lookup failed on %s: %s", path, exc)

        seen = set()
        deduped: list[dict[str, Any]] = []
        for row in rows:
            key = (
                row.get("id"),
                row.get("id_item"),
                row.get("item_name") or row.get("name"),
                row.get("terminal_name") or row.get("name_terminal"),
            )
            if key in seen:
                continue
            seen.add(key)
            deduped.append(row)

        return deduped

    async def price_snapshot(self, commodity: str) -> list[dict[str, Any]]:
        for path in ("/commodities_prices", "/commodities"):
            try:
                data = await self._get(path, params={"search": commodity, "limit": 100})
                if isinstance(data, list):
                    return [x for x in data if isinstance(x, dict)]
            except Exception as exc:
                log.debug("UEX price snapshot failed on %s: %s", path, exc)
        return []
