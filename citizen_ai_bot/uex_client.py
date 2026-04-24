from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Any

import httpx

from .config import settings
from .utils import fuzzy_score

log = logging.getLogger(__name__)

_CACHE_TTL = 60 * 60 * 12  # 12 hours
_SHIP_COMPONENT_CATEGORY_IDS = tuple(range(1, 9))
_FULL_ITEM_CATEGORY_IDS = tuple(range(1, 31))
_BLOCKED_LOADOUT_TERMS = {
    "armor",
    "helmet",
    "undersuit",
    "backpack",
    "torso",
    "legs",
    "arms",
    "clothing",
    "personal weapons",
    "magazine",
    "ammo",
    "food",
    "drink",
    "medical",
}
_LOADOUT_SCOPE_HINTS = {
    "ship_weapon": ("weapon", "repeater", "cannon", "distortion", "gatling", "scattergun", "ship weapons"),
    "missile": ("missile", "torpedo", "rack"),
    "shield": ("shield", "generator"),
    "power": ("power", "plant"),
    "cooler": ("cooler", "cooling"),
    "quantum": ("quantum", "drive"),
    "ship_component": ("shield", "power", "cooler", "cooling", "quantum", "weapon", "repeater", "cannon", "missile"),
}


def _normalize_text(text: str) -> str:
    text = text.lower().strip().replace("-", " ")
    text = re.sub(r"\biii\b", "3", text)
    text = re.sub(r"\bii\b", "2", text)
    text = re.sub(r"\biv\b", "4", text)
    text = re.sub(r"\bv\b", "5", text)
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    return " ".join(text.split())


def _compact_text(text: str) -> str:
    return _normalize_text(text).replace(" ", "")


def _item_blob(item: dict[str, Any]) -> str:
    values = []
    for key in ("name", "slug", "category", "section", "company_name", "type", "kind", "class", "subtype"):
        value = item.get(key)
        if value:
            values.append(str(value))
    return _normalize_text(" ".join(values))


class UEXClient:
    def __init__(self) -> None:
        headers = {"Accept": "application/json", "User-Agent": "CitizenAI-DiscordBot/1.0"}
        if settings.uex_api_token:
            headers["Authorization"] = f"Bearer {settings.uex_api_token}"
        self._http = httpx.AsyncClient(base_url=settings.uex_api_base.rstrip("/"), timeout=20.0, follow_redirects=True, headers=headers)
        self._items_cache: tuple[float, list[dict[str, Any]]] | None = None
        self._component_items_cache: tuple[float, list[dict[str, Any]]] | None = None
        self._terminals_cache: tuple[float, list[dict[str, Any]]] | None = None
        self._distance_cache: dict[tuple[int, int], tuple[float, float | None]] = {}
        self._items_lock = asyncio.Lock()
        self._component_items_lock = asyncio.Lock()

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
        for path, params in (("/items", {"id_category": 1}), ("/star_systems", {})):
            try:
                if await self._get(path, params=params) is not None:
                    return True
            except Exception as exc:
                log.debug("UEX ping failed on %s: %s", path, exc)
        return False

    async def _load_category_items(self, category_ids: tuple[int, ...]) -> list[dict[str, Any]]:
        all_items: list[dict[str, Any]] = []
        for category_id in category_ids:
            try:
                data = await self._get("/items", params={"id_category": category_id})
                if isinstance(data, list):
                    all_items.extend(x for x in data if isinstance(x, dict))
            except Exception as exc:
                log.debug("UEX items index load failed for category %s: %s", category_id, exc)
        deduped: dict[str, dict[str, Any]] = {}
        for item in all_items:
            key = str(item.get("id") or item.get("uuid") or item.get("slug") or item.get("name"))
            if key and key != "None":
                deduped[key] = item
        return list(deduped.values())

    async def _load_items_index(self) -> list[dict[str, Any]]:
        now = time.monotonic()
        if self._items_cache and (now - self._items_cache[0]) < _CACHE_TTL:
            return self._items_cache[1]
        async with self._items_lock:
            now = time.monotonic()
            if self._items_cache and (now - self._items_cache[0]) < _CACHE_TTL:
                return self._items_cache[1]
            result = await self._load_category_items(_FULL_ITEM_CATEGORY_IDS)
            self._items_cache = (now, result)
            log.info("Loaded %s items into full UEX item index", len(result))
            return result

    async def _load_component_items_index(self) -> list[dict[str, Any]]:
        now = time.monotonic()
        if self._component_items_cache and (now - self._component_items_cache[0]) < _CACHE_TTL:
            return self._component_items_cache[1]
        async with self._component_items_lock:
            now = time.monotonic()
            if self._component_items_cache and (now - self._component_items_cache[0]) < _CACHE_TTL:
                return self._component_items_cache[1]
            result = await self._load_category_items(_SHIP_COMPONENT_CATEGORY_IDS)
            self._component_items_cache = (now, result)
            log.info("Loaded %s items into scoped UEX ship-component index", len(result))
            return result

    async def _load_terminals_index(self) -> list[dict[str, Any]]:
        now = time.monotonic()
        if self._terminals_cache and (now - self._terminals_cache[0]) < _CACHE_TTL:
            return self._terminals_cache[1]
        terminals: list[dict[str, Any]] = []
        try:
            data = await self._get("/terminals")
            if isinstance(data, list):
                terminals = [x for x in data if isinstance(x, dict)]
        except Exception as exc:
            log.debug("UEX full terminal lookup failed: %s", exc)
        self._terminals_cache = (now, terminals)
        log.info("Loaded %s terminals into local UEX index", len(terminals))
        return terminals

    def _scope_match(self, item: dict[str, Any], scope: str | None) -> bool:
        if not scope:
            return True
        blob = _item_blob(item)
        if any(term in blob for term in _BLOCKED_LOADOUT_TERMS):
            return False
        hints = _LOADOUT_SCOPE_HINTS.get(scope) or _LOADOUT_SCOPE_HINTS["ship_component"]
        return any(hint in blob for hint in hints)

    def _pick_best_item(self, query: str, items: list[dict[str, Any]], scope: str | None = None) -> dict[str, Any] | None:
        ranked: list[tuple[float, dict[str, Any]]] = []
        query_norm = _normalize_text(query)
        query_compact = _compact_text(query)
        for item in items:
            if not self._scope_match(item, scope):
                continue
            names = [item.get("name"), item.get("slug"), item.get("uuid"), item.get("category"), item.get("section"), item.get("company_name")]
            names = [str(x) for x in names if x]
            if not names:
                continue
            norm_names = [_normalize_text(name) for name in names]
            compact_names = [_compact_text(name) for name in names]
            score = max(fuzzy_score(query, name) for name in names)
            if any(query_norm == n for n in norm_names):
                score += 65
            if any(query_norm in n or n in query_norm for n in norm_names):
                score += 20
            if any(query_compact == n for n in compact_names):
                score += 45
            if any(query_compact in n or n in query_compact for n in compact_names):
                score += 15
            ranked.append((score, item))
        if not ranked:
            return None
        ranked.sort(key=lambda x: x[0], reverse=True)
        best_score, best_item = ranked[0]
        if best_score < (70 if scope else 50):
            log.warning("Rejected weak UEX item match for %r scope=%r score=%s", query, scope, best_score)
            return None
        log.info("Resolved UEX item %r -> %r scope=%r score=%s", query, best_item.get("name"), scope, best_score)
        return best_item

    async def resolve_item(self, name: str) -> dict[str, Any] | None:
        items = await self._load_items_index()
        return self._pick_best_item(name, items)

    async def resolve_ship_component(self, name: str, scope: str | None = "ship_component") -> dict[str, Any] | None:
        items = await self._load_component_items_index()
        return self._pick_best_item(name, items, scope=scope)

    async def resolve_ship_components(self, names_by_scope: list[tuple[str, str | None]]) -> dict[str, dict[str, Any] | None]:
        items = await self._load_component_items_index()
        resolved: dict[str, dict[str, Any] | None] = {}
        for name, scope in names_by_scope:
            resolved[name] = self._pick_best_item(name, items, scope=scope or "ship_component")
        return resolved

    async def resolve_terminal(self, location: str) -> dict[str, Any] | None:
        query = _normalize_text(location)
        aliases = {"orison": "Seraphim Station", "seraphim": "Seraphim Station", "port tressler": "Port Tressler", "tressler": "Port Tressler", "everus": "Everus Harbor", "everus harbor": "Everus Harbor", "grimhex": "GrimHEX", "grim hex": "GrimHEX", "area18": "Area 18", "area 18": "Area 18", "new babbage": "New Babbage", "nb": "New Babbage", "lorville": "Lorville"}
        search_term = aliases.get(query, location)
        candidates = await self._load_terminals_index()
        if not candidates:
            return None
        ranked: list[tuple[float, dict[str, Any]]] = []
        search_norm = _normalize_text(search_term)
        search_compact = _compact_text(search_term)
        for terminal in candidates:
            names = [terminal.get("name"), terminal.get("fullname"), terminal.get("displayname"), terminal.get("nickname"), terminal.get("code"), terminal.get("city_name"), terminal.get("planet_name"), terminal.get("moon_name"), terminal.get("orbit_name")]
            names = [str(x) for x in names if x]
            if not names:
                continue
            score = max(fuzzy_score(search_term, name) for name in names)
            norm_names = [_normalize_text(n) for n in names]
            compact_names = [_compact_text(n) for n in names]
            lower_name = " ".join(norm_names)
            if any(search_norm == n for n in norm_names):
                score += 50
            if any(search_norm in n for n in norm_names):
                score += 20
            if any(search_compact == n for n in compact_names):
                score += 40
            if any(search_compact in n for n in compact_names):
                score += 15
            if "admin" in lower_name:
                score -= 40
            if "cargo" in lower_name or "factory line" in lower_name:
                score -= 20
            if "station" in lower_name or "harbor" in lower_name or "port" in lower_name:
                score += 15
            ranked.append((score, terminal))
        if not ranked:
            return None
        ranked.sort(key=lambda x: x[0], reverse=True)
        return ranked[0][1]

    async def get_terminal_distance(self, origin_terminal_id: int, destination_terminal_id: int) -> float | None:
        cache_key = (origin_terminal_id, destination_terminal_id)
        now = time.monotonic()
        cached = self._distance_cache.get(cache_key)
        if cached and (now - cached[0]) < _CACHE_TTL:
            return cached[1]
        try:
            data = await self._get("/terminals_distances", params={"id_terminal_origin": origin_terminal_id, "id_terminal_destination": destination_terminal_id})
        except Exception as exc:
            log.debug("UEX terminal distance lookup failed: %s", exc)
            self._distance_cache[cache_key] = (now, None)
            return None
        distance = None
        if isinstance(data, dict) and data.get("distance") is not None:
            try:
                distance = float(data.get("distance"))
            except Exception:
                distance = None
        self._distance_cache[cache_key] = (now, distance)
        return distance

    async def get_item_locations(self, name: str, location: str | None = None) -> list[dict[str, Any]]:
        item = await self.resolve_item(name)
        if not item:
            log.warning("No UEX item resolved for query %r", name)
            return []
        resolved_item_name = item.get("name") or item.get("slug") or name
        lookup_attempts: list[dict[str, Any]] = []
        if item.get("id") is not None:
            lookup_attempts.append({"id_item": item.get("id")})
        if item.get("uuid"):
            lookup_attempts.append({"uuid": item.get("uuid")})
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
        deduped = []
        for row in rows:
            key = (row.get("id"), row.get("id_item"), row.get("id_terminal"), row.get("terminal_name"))
            if key in seen:
                continue
            seen.add(key)
            row["_resolved_item"] = resolved_item_name
            deduped.append(row)
        if not location:
            deduped.sort(key=lambda row: (row.get("price_buy") is None and row.get("price_sell") is None, row.get("terminal_name") or ""))
            return deduped
        origin_terminal = await self.resolve_terminal(location)
        if not origin_terminal or origin_terminal.get("id") is None:
            return deduped
        resolved_location_name = origin_terminal.get("displayname") or origin_terminal.get("fullname") or origin_terminal.get("name")
        for row in deduped:
            row["_resolved_location"] = resolved_location_name
            try:
                row["_distance_gm"] = await self.get_terminal_distance(int(origin_terminal["id"]), int(row["id_terminal"])) if row.get("id_terminal") is not None else None
            except Exception:
                row["_distance_gm"] = None
        deduped.sort(key=lambda row: (row.get("_distance_gm") is None, row.get("_distance_gm") if row.get("_distance_gm") is not None else 10**12, row.get("terminal_name") or ""))
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
