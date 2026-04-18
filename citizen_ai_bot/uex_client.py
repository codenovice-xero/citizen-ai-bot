from __future__ import annotations

from typing import Any

import httpx

from .config import settings


class UEXClient:
    def __init__(self) -> None:
        headers = {
            "Accept": "application/json",
            "User-Agent": "CitizenAI-DiscordBot/0.3",
        }
        if settings.uex_api_token.strip():
            headers["Authorization"] = f"Bearer {settings.uex_api_token.strip()}"

        self._client = httpx.AsyncClient(
            base_url=settings.uex_api_base.rstrip("/"),
            timeout=settings.request_timeout_seconds,
            headers=headers,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        response = await self._client.get(path, params=params)
        response.raise_for_status()
        data = response.json()
        if isinstance(data, dict):
            return data
        return {"data": data}

    async def ping(self) -> bool:
        try:
            await self.get("/star_systems")
            return True
        except Exception:
            return False
