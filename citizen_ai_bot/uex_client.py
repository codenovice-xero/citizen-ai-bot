from __future__ import annotations

import logging
import re
import time
from typing import Any

import httpx

from .config import settings
from .utils import fuzzy_score

log = logging.getLogger(__name__)

_CACHE_TTL = 60 * 60 * 12  # 12 hours


def _normalize_text(text: str) -> str:
    text = text.lower().strip()
    text = text.replace("-", " ")
    text = re.sub(r"\biii\b", "3", text)
    text = re.sub(r"\bii\b", "2", text)
    text = re.sub(r"\biv\b", "4", text)
    text = re.sub(r"\bv\b", "5", text)
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    text = " ".join(text.split())
    return text


def _compact_text(text: str) -> str:
    return _normalize_text(text).replace(" ", "")


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
        self._terminals_cache: tuple[float, list[dict[str, Any]]] | None = None

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
        probes: list[tuple[str, dict[str, Any]]] = [
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

    def _pick_best_item(self, query: str, items: list[dict[str, Any]]) -> dict[str, Any] | None:
        ranked: list[tuple[float, dict[str, Any]]] = []
        query_norm = _normalize_text(query)
        query_compact = _compact_text(query)

        weaponish_query = any(token in query_compact for token in [
            "p4ar", "p4", "ar", "rifle", "gun", "smg", "shotgun", "sniper", "lmg", "pistol", "launcher"
        ])

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

            norm_names = [_normalize_text(name) for name in names]
            compact_names = [_compact_text(name) for name in names]
            item_name = str(item.get("name", ""))

            if any(query_norm == n for n in norm_names):
                score += 45
            if any(query_norm in n for n in norm_names):
                score += 20
            if any(query_compact == n for n in compact_names):
                score += 35
            if any(query_compact in n for n in compact_names):
                score += 15

            lower_name = item_name.lower()
            compact_name = _compact_text(item_name)

            if weaponish_query:
                if "magazine" in lower_name or "ammo" in lower_name or "battery" in lower_name or "clip" in lower_name:
                    score -= 40
                if "rifle" in lower_name or "carbine" in lower_name or "smg" in lower_name or "pistol" in lower_name:
                    score += 12

            if query_compact == "p4ar":
                if "p4ar" in compact_name and "magazine" not in lower_name:
                    score += 60
                if "magazine" in lower_name:
                    score -= 60

            ranked.append((score, item))

        if not ranked:
            return None

        ranked.sort(key=lambda x: x[0], reverse=True)
        best_score, best_item = ranked[0]
        best_name = str(best_item.get("name", ""))

        if best_score < 50:
            log.warning(
                "Rejected weak UEX item match for %r: %r (score=%s)",
                query,
                best_name,
                best_score,
            )
            return None

        log.info(
            "Resolved UEX item %r -> %r (id=%r, score=%s)",
            query,
            best_name,
            best_item.get("id"),
            best_score,
        )
        return best_item

    async def resolve_item(self, name: str) -> dict[str, Any] | None:
        items = await self._load_items_index()
        return self._pick_best_item(name, items)

    async def resolve_terminal(self, location: str) -> dict[str, Any] | None:
        query = _normalize_text(location)

        terminal_aliases = {
            "orison": "Seraphim",
            "seraphim": "Seraphim",
            "area18": "Area 18",
            "area 18": "Area 18",
            "new babbage": "New Babbage",
            "nb": "New Babbage",
            "lorville": "Lorville",
            "everus": "Everus Harbor",
            "everus harbor": "Everus Harbor",
            "port tressler": "Port Tressler",
            "tressler": "Port Tressler",
            "grimhex": "GrimHEX",
            "grim hex": "GrimHEX",
        }

        search_term = terminal_aliases.get(query, location)
        candidates = await self._load_terminals_index()
        if not candidates:
            return None

        ranked: list[tuple[float, dict[str, Any]]] = []
        search_norm = _normalize_text(search_term)
        search_compact = _compact_text(search_term)

        for terminal in candidates:
            names = [
                terminal.get("name"),
                terminal.get("fullname"),
                terminal.get("displayname"),
                terminal.get("nickname"),
                terminal.get("code"),
                terminal.get("city_name"),
                terminal.get("planet_name"),
                terminal.get("moon_name"),
                terminal.get("orbit_name"),
            ]
            names = [str(x) for x in names if x]
            if not names:
                continue

            score = max(fuzzy_score(search_term, name) for name in names)

            norm_names = [_normalize_text(n) for n in names]
            compact_names = [_compact_text(n) for n in names]

            if any(search_norm == n for n in norm_names):
                score += 50
            if any(search_norm in n for n in norm_names):
                score += 20
            if any(search_compact == n for n in compact_names):
                score += 40
            if any(search_compact in n for n in compact_names):
                score += 15

            ranked.append((score, terminal))

        if not ranked:
            return None

        ranked.sort(key=lambda x: x[0], reverse=True)
        best_score, best_terminal = ranked[0]

        log.info(
            "Resolved terminal %r -> %r (id=%r, score=%s)",
            location,
            best_terminal.get("name") or best_terminal.get("displayname"),
            best_terminal.get("id"),
            best_score,
        )
        return best_terminal

    async def get_terminal_distances(self, origin_terminal_id: int) -> dict[str, float]:
        distance_map: dict[str, float] = {}

        attempts = [
            {"id_terminal_origin": origin_terminal_id},
            {"id_terminal": origin_terminal_id},
            {"id_terminal_from": origin_terminal_id},
        ]

        for params in attempts:
            try:
                data = await self._get("/terminals_distances", params=params)
            except Exception as exc:
                log.debug("UEX terminal distance lookup failed for %s: %s", params, exc)
                continue

            if not isinstance(data, list):
                continue

            for row in data:
                if not isinstance(row, dict):
                    continue

                dest_id = (
                    row.get("id_terminal_destination")
                    or row.get("id_terminal_to")
                    or row.get("id_terminal")
                    or row.get("terminal_id")
                )
                distance = row.get("distance") or row.get("distance_gm") or row.get("dist")

                try:
                    if dest_id is not None and distance is not None:
                        distance_map[str(dest_id)] = float(distance)
                except Exception:
                    continue

            if distance_map:
                log.info("Resolved %s terminal distances from %s", len(distance_map), origin_terminal_id)
                return distance_map

        log.warning("No terminal distance map returned for origin terminal %s", origin_terminal_id)
        return {}

    async def get_item_locations(self, name: str, location: str | None = None) -> list[dict[str, Any]]:
        item = await self.resolve_item(name)
        if not item:
            log.warning("No UEX item resolved for query %r", name)
            return []

        resolved_item_name = item.get("name") or item.get("slug") or name
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

        if not location:
            for row in deduped:
                row["_resolved_item"] = resolved_item_name

            deduped.sort(
                key=lambda row: (
                    row.get("price_buy") is None and row.get("price_sell") is None,
                    row.get("terminal_name") or "",
                )
            )
            return deduped

        origin_terminal = await self.resolve_terminal(location)
        if not origin_terminal:
            log.warning("No UEX terminal resolved for location %r", location)
            for row in deduped:
                row["_resolved_item"] = resolved_item_name
            return deduped

        origin_terminal_id = origin_terminal.get("id")
        if origin_terminal_id is None:
            for row in deduped:
                row["_resolved_item"] = resolved_item_name
            return deduped

        resolved_location_name = (
            origin_terminal.get("displayname")
            or origin_terminal.get("fullname")
            or origin_terminal.get("name")
        )

        distance_map = await self.get_terminal_distances(int(origin_terminal_id))

        for row in deduped:
            terminal_id = row.get("id_terminal")
            try:
                row["_distance_gm"] = distance_map.get(str(terminal_id)) if terminal_id is not None else None
            except Exception:
                row["_distance_gm"] = None
            row["_resolved_location"] = resolved_location_name
            row["_resolved_item"] = resolved_item_name

        deduped.sort(
            key=lambda row: (
                row.get("_distance_gm") is None,
                row.get("_distance_gm") if row.get("_distance_gm") is not None else 10**12,
                row.get("terminal_name") or "",
            )
        )

        if deduped:
            preview = [
                (
                    row.get("terminal_name"),
                    row.get("_distance_gm"),
                    row.get("price_buy"),
                    row.get("price_sell"),
                )
                for row in deduped[:5]
            ]
            log.info("Nearest item results preview for %r from %r: %s", name, location, preview)

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
