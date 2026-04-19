from __future__ import annotations

from typing import Any

import httpx


class WikiClient:
    def __init__(self) -> None:
        self._client = httpx.AsyncClient(
            base_url="https://api.star-citizen.wiki",
            timeout=20.0,
            headers={
                "Accept": "application/json",
                "User-Agent": "CitizenAI-DiscordBot/0.1",
            },
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
