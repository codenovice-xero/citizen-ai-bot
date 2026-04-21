from __future__ import annotations

import logging
from typing import Any

import httpx

log = logging.getLogger(__name__)


class UEXClient:
    """
    Thin async client for the public UEX API 2.0.
    Docs currently advertise endpoints like:
    - /2.0/items?uuid={string}
    - /2.0/items_prices?uuid={string}
    - /2.0/commodities_prices?commodity_name={string}
    - /2.0/game_versions
    """

    def __init__(self, api_token: str | None = None, timeout: float = 20.0) -> None:
        headers = {
            "Accept": "application/json",
            "User-Agent": "CitizenAI-DiscordBot/1.0",
        }
        if api_token:
            headers["Authorization"] = f"Bearer {api_token}"
        self._http = httpx.AsyncClient(
            base_url="https://api.uexcorp.space",
            timeout=timeout,
            follow_redirects=True,
            headers=headers,
        )

    async def close(self) -> None:
        await self._http.aclose()

    async def _get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        response = await self._http.get(path, params=params)
        response.raise_for_status()
        payload = response.json()

        if isinstance(payload, dict):
            for key in ("data", "items", "results"):
                value = payload.get(key)
                if value is not None:
                    return value
        return payload

    async def ping(self) -> bool:
        for path in ("/2.0/game_versions", "/2.0/commodities"):
            try:
                payload = await self._get_json(path)
                if payload:
                    return True
            except Exception:
                continue
        return False

    async def get_item_by_uuid(self, uuid: str) -> list[dict[str, Any]]:
        try:
            data = await self._get_json("/2.0/items", params={"uuid": uuid})
        except Exception as exc:
            log.warning("UEX item lookup failed for %s: %s", uuid, exc)
            return []
        return [row for row in (data if isinstance(data, list) else [data]) if isinstance(row, dict)]

    async def get_item_prices_by_uuid(self, uuid: str) -> list[dict[str, Any]]:
        try:
            data = await self._get_json("/2.0/items_prices", params={"uuid": uuid})
        except Exception as exc:
            log.warning("UEX item price lookup failed for %s: %s", uuid, exc)
            return []
        return [row for row in (data if isinstance(data, list) else [data]) if isinstance(row, dict)]

    async def get_commodity_prices(self, commodity_name: str) -> list[dict[str, Any]]:
        try:
            data = await self._get_json("/2.0/commodities_prices", params={"commodity_name": commodity_name})
        except Exception as exc:
            log.warning("UEX commodity price lookup failed for %r: %s", commodity_name, exc)
            return []
        return [row for row in (data if isinstance(data, list) else [data]) if isinstance(row, dict)]

    async def get_commodity_prices_by_code(self, commodity_code: str) -> list[dict[str, Any]]:
        try:
            data = await self._get_json("/2.0/commodities_prices", params={"commodity_code": commodity_code})
        except Exception as exc:
            log.warning("UEX commodity code lookup failed for %r: %s", commodity_code, exc)
            return []
        return [row for row in (data if isinstance(data, list) else [data]) if isinstance(row, dict)]
