from __future__ import annotations

import logging
import time
from typing import Any

import httpx

log = logging.getLogger(__name__)

_ERKUL_API_BASE = "https://erkul.games/api/v2"
_CACHE_TTL = 60 * 30  # 30 minutes


def _norm_ship_name(name: str) -> str:
    """Normalise a ship name for comparison: lowercase, strip whitespace."""
    return " ".join((name or "").strip().lower().split())


class ErkulClient:
    """Async client for the erkul.games ship data API.

    Fetches ship definitions including hardpoint configurations, component
    specifications, and performance metrics.  Results are cached in-process
    for ``_CACHE_TTL`` seconds to avoid hammering the upstream API.
    """

    def __init__(self, timeout: float = 20.0) -> None:
        self._http = httpx.AsyncClient(
            base_url=_ERKUL_API_BASE,
            timeout=timeout,
            headers={
                "Accept": "application/json",
                "User-Agent": "CitizenAI-DiscordBot/0.3",
            },
        )
        # Full ship list cache: (timestamp, list[dict])
        self._ships_cache: tuple[float, list[dict[str, Any]]] | None = None
        # Per-ship detail cache: ship_key -> (timestamp, dict)
        self._ship_detail_cache: dict[str, tuple[float, dict[str, Any]]] = {}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def close(self) -> None:
        await self._http.aclose()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _fetch_ships_list(self) -> list[dict[str, Any]]:
        """Return the full ship list, using the in-process cache when fresh."""
        now = time.monotonic()
        if self._ships_cache is not None:
            ts, data = self._ships_cache
            if (now - ts) < _CACHE_TTL:
                return data

        response = await self._http.get("/ships")
        response.raise_for_status()
        payload = response.json()

        # The API may return a list directly or wrap it in a "data" key.
        if isinstance(payload, list):
            ships: list[dict[str, Any]] = payload
        elif isinstance(payload, dict):
            ships = payload.get("data") or payload.get("ships") or []
        else:
            ships = []

        self._ships_cache = (now, ships)
        return ships

    def _find_ship_in_list(
        self, ships: list[dict[str, Any]], ship_name: str
    ) -> dict[str, Any] | None:
        """Find the best-matching ship entry from the list by name."""
        target = _norm_ship_name(ship_name)
        if not target:
            return None

        # 1. Exact normalised match
        for ship in ships:
            candidate = _norm_ship_name(str(ship.get("name") or ship.get("shipName") or ""))
            if candidate == target:
                return ship

        # 2. Substring / prefix match
        for ship in ships:
            candidate = _norm_ship_name(str(ship.get("name") or ship.get("shipName") or ""))
            if target in candidate or candidate in target:
                return ship

        return None

    @staticmethod
    def _extract_hardpoints(ship_data: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
        """Parse raw ship data into categorised hardpoint buckets.

        Returns a dict with keys: ``weapons``, ``shields``, ``power``,
        ``coolers``, ``missiles``, ``other``.
        """
        buckets: dict[str, list[dict[str, Any]]] = {
            "weapons": [],
            "shields": [],
            "power": [],
            "coolers": [],
            "missiles": [],
            "other": [],
        }

        # erkul.games ships may expose hardpoints under several keys.
        raw_hardpoints: list[Any] = (
            ship_data.get("hardpoints")
            or ship_data.get("loadout")
            or ship_data.get("components")
            or []
        )

        for hp in raw_hardpoints:
            if not isinstance(hp, dict):
                continue

            hp_type = str(
                hp.get("type") or hp.get("category") or hp.get("itemType") or ""
            ).lower()
            component = hp.get("component") or hp.get("item") or {}
            if isinstance(component, str):
                component = {"name": component}

            entry: dict[str, Any] = {
                "slot": hp.get("slot") or hp.get("name") or hp.get("hardpointName"),
                "size": hp.get("size") or hp.get("maxSize") or component.get("size"),
                "component_name": component.get("name") or component.get("itemName"),
                "component_class": component.get("class") or component.get("grade"),
                "manufacturer": component.get("manufacturer") or component.get("brand"),
                "raw": hp,
            }

            if any(kw in hp_type for kw in ("weapon", "gun", "cannon", "laser", "ballistic", "repeater")):
                buckets["weapons"].append(entry)
            elif any(kw in hp_type for kw in ("shield",)):
                buckets["shields"].append(entry)
            elif any(kw in hp_type for kw in ("power", "powerplant", "qig")):
                buckets["power"].append(entry)
            elif any(kw in hp_type for kw in ("cooler",)):
                buckets["coolers"].append(entry)
            elif any(kw in hp_type for kw in ("missile", "rocket", "torpedo")):
                buckets["missiles"].append(entry)
            else:
                buckets["other"].append(entry)

        return buckets

    @staticmethod
    def _extract_performance(ship_data: dict[str, Any]) -> dict[str, Any]:
        """Pull top-level performance metrics out of raw ship data."""
        perf: dict[str, Any] = {}

        # Speed / flight
        for key in ("scmSpeed", "maxSpeed", "afterburnerSpeed", "scm_speed", "max_speed"):
            val = ship_data.get(key)
            if val is not None:
                perf.setdefault("scm_speed", val) if "scm" in key.lower() else perf.setdefault("max_speed", val)

        # Shields
        for key in ("shieldHp", "shieldHealth", "shield_hp"):
            val = ship_data.get(key)
            if val is not None:
                perf["shield_hp"] = val
                break

        # Hull
        for key in ("hullHp", "hullHealth", "hull_hp"):
            val = ship_data.get(key)
            if val is not None:
                perf["hull_hp"] = val
                break

        # Cargo
        for key in ("cargoCapacity", "cargo", "cargo_capacity"):
            val = ship_data.get(key)
            if val is not None:
                perf["cargo_scu"] = val
                break

        # Crew
        for key in ("crewSize", "maxCrew", "crew"):
            val = ship_data.get(key)
            if val is not None:
                perf["max_crew"] = val
                break

        return perf

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get_ship(self, ship_name: str) -> dict[str, Any] | None:
        """Fetch raw ship data for *ship_name* from erkul.games.

        Returns the raw ship dict on success, or ``None`` if the ship is not
        found or the API is unreachable.  Results are cached per ship for
        ``_CACHE_TTL`` seconds.
        """
        key = _norm_ship_name(ship_name)
        if not key:
            return None

        now = time.monotonic()
        cached = self._ship_detail_cache.get(key)
        if cached is not None:
            ts, data = cached
            if (now - ts) < _CACHE_TTL:
                return data

        try:
            ships = await self._fetch_ships_list()
        except httpx.HTTPError as exc:
            log.warning("erkul.games ship list fetch failed: %s", exc)
            return None
        except Exception as exc:
            log.warning("erkul.games unexpected error fetching ship list: %s", exc)
            return None

        match = self._find_ship_in_list(ships, ship_name)
        if match is None:
            log.debug("erkul.games: no match found for ship %r", ship_name)
            return None

        # Some API shapes embed full detail in the list; others require a
        # follow-up request using an id / slug field.
        ship_id = match.get("id") or match.get("slug") or match.get("shipCode")
        if ship_id and not match.get("hardpoints") and not match.get("loadout"):
            try:
                resp = await self._http.get(f"/ships/{ship_id}")
                resp.raise_for_status()
                detail_payload = resp.json()
                if isinstance(detail_payload, dict):
                    match = detail_payload.get("data") or detail_payload
            except httpx.HTTPError as exc:
                log.warning("erkul.games detail fetch failed for %r: %s", ship_name, exc)
                # Fall through with the list-level data we already have.
            except Exception as exc:
                log.warning("erkul.games unexpected error fetching ship detail for %r: %s", ship_name, exc)

        self._ship_detail_cache[key] = (now, match)
        return match

    async def get_hardpoints(self, ship_name: str) -> dict[str, list[dict[str, Any]]] | None:
        """Return categorised hardpoint buckets for *ship_name*.

        Returns a dict with keys ``weapons``, ``shields``, ``power``,
        ``coolers``, ``missiles``, ``other``, or ``None`` if the ship cannot
        be found or the API is unavailable.
        """
        ship_data = await self.get_ship(ship_name)
        if ship_data is None:
            return None
        return self._extract_hardpoints(ship_data)

    async def get_performance(self, ship_name: str) -> dict[str, Any] | None:
        """Return a flat dict of performance metrics for *ship_name*.

        Returns ``None`` if the ship cannot be found or the API is unavailable.
        """
        ship_data = await self.get_ship(ship_name)
        if ship_data is None:
            return None
        return self._extract_performance(ship_data)
