from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from .config import settings
from .utils import fuzzy_score

log = logging.getLogger(__name__)

_CACHE_TTL = 60 * 60 * 12  # 12 hours


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
        self._items_cache: tuple[float, list[dict[str, Any]]] | None = None

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
        # Use only documented parameter shapes.
        probes: list[tuple[str, dict[str, Any]]] = [
            ("/commodities_prices", {"id_terminal": 1}),
            ("/items", {"id_category": 1}),
            ("/star_systems", {}),
        ]
        for path, params in probes:
            try:
                data = await self._get(path, params=params)
                if data is not None:
                    return True
            except Exception as exc:
                log.debug("UEX ping failed on %s: %s", path, exc)
        return False

    async def _load_items_index(self) -> list[dict[str, Any]]:
        now = time.monotonic()
        if self._items_cache and (now - self._items_cache[0]) < _CACHE_TTL:
            return self._items_cache[1]

        all_items: list[dict[str, Any]] = []

        # /items requires a valid id_category.
        # Pull a useful spread of categories and cache locally.
        for category_id in range(1, 31):
            try:
                data = await self._get("/items", params={"id_category": category_id})
                if isinstance(data, list):
                    all_items.extend(x for x in data if isinstance(x, dict))
            except Exception as exc:
                log.debug("UEX items index load failed for category %s: %s", category_id, exc)

        deduped: dict[int, dict[str, Any]] = {}
        for item in all_items:
            item_id = item.get("id")
            if isinstance(item_id, int):
                deduped[item_id] = item

        result = list(deduped.values())
        self._items_cache = (now, result)
        log.info("Loaded %s items into local UEX index", len(result))
        return result

    def _pick_best_item(self, query: str, items: list[dict[str, Any]]) -> dict[str, Any] | None:
        ranked: list[tuple[float, dict[str, Any]]] = []
        query_norm = " ".join(query.lower().split())

        for item in items:
            names = [
                item.get("name"),
                item.get("slug"),
                item.get("uuid"),
                item.get("category"),
                item.get("section"),
                item.get("company_name"),
            ]
            names = [str(x) for x in names if x]

            if not names:
                continue

            score = max(fuzzy_score(query, name) for name in names)
            lowered_names = [name.lower() for name in names]

            if any(query_norm == name for name in lowered_names):
                score += 40
            if any(query_norm in name for name in lowered_names):
                score += 20

            ranked.append((score, item))

        if not ranked:
            return None

        ranked.sort(key=lambda x: x[0], reverse=True)
        best_score, best_item = ranked[0]

        best_name = str(best_item.get("name", "")).lower()
        if query_norm not in best_name and best_score < 70:
            log.warning(
                "Rejected weak UEX item match for %r: %r (score=%s)",
                query,
                best_item.get("name"),
                best_score,
            )
            return None

        log.info("Resolved UEX item %r -> %r (id=%r)", query, best_item.get("name"), best_item.get("id"))
        return best_item

    async def resolve_item(self, name: str) -> dict[str, Any] | None:
        items = await self._load_items_index()
        return self._pick_best_item(name, items)

    async def get_item_locations(self, name: str) -> list[dict[str, Any]]:
        item = await self.resolve_item(name)
        if not item:
            log.warning("No UEX item resolved for query %r", name)
            return []

        item_id = item.get("id")
        item_uuid = item.get("uuid")

        lookup_attempts: list[dict[str, Any]] = []
        if item_id is not None:
            lookup_attempts.append({"id_item": item_id})
        if item_uuid:
            lookup_attempts.append({"uuid": item_uuid})

        rows: list[dict[str, Any]] = []
        for params in lookup_attempts:
            try:
                data = await self._get("/items_prices", params=params)
                if isinstance(data, list) and data:
                    rows.extend(x for x in data if isinstance(x, dict))
                    break
            except Exception as exc:
                log.debug("UEX item price lookup failed for %s: %s", params, exc)

        seen = set()
        deduped: list[dict[str, Any]] = []
        for row in rows:
            key = (
                row.get("id"),
                row.get("id_item"),
                row.get("id_terminal"),
                row.get("terminal_name"),
            )
            if key in seen:
                continue
            seen.add(key)
            deduped.append(row)

        deduped.sort(
            key=lambda row: (
                row.get("price_buy") is None and row.get("price_sell") is None,
                row.get("terminal_name") or "",
            )
        )
        return deduped

    async def price_snapshot(self, commodity: str) -> list[dict[str, Any]]:
        # Leaving this as-is unless /trend needs deeper fixes.
        for path in ("/commodities_prices", "/commodities"):
            try:
                data = await self._get(path, params={"search": commodity, "limit": 100})
                if isinstance(data, list):
                    return [x for x in data if isinstance(x, dict)]
            except Exception as exc:
                log.debug("UEX price snapshot failed on %s: %s", path, exc)
        return []
