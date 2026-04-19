from __future__ import annotations

import logging
import time
from typing import Any

import httpx

log = logging.getLogger(__name__)

_WIKI_API_BASE = "https://api.star-citizen.wiki/api/v2"
_CACHE_TTL = 60 * 30  # 30 minutes


def _norm_ship_name(name: str) -> str:
    """Normalise a ship name for comparison: lowercase, strip whitespace."""
    return " ".join((name or "").strip().lower().split())


class WikiClient:
    """Async client for the Star Citizen Wiki ship data API.

    Fetches ship definitions including hardpoint configurations, component
    specifications, and performance metrics.  Results are cached in-process
    for ``_CACHE_TTL`` seconds to avoid hammering the upstream API.
    """

    def __init__(self, timeout: float = 20.0) -> None:
        self._http = httpx.AsyncClient(
            base_url=_WIKI_API_BASE,
            timeout=timeout,
            follow_redirects=True,
            headers={
                "Accept": "application/json",
                "User-Agent": "CitizenAI-DiscordBot/0.3",
            },
        )
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

    async def _fetch_ship_data(self, ship_name: str) -> dict[str, Any] | None:
        """Query the Wiki API for *ship_name* and return the raw ship dict.

        The Star Citizen Wiki API exposes individual vehicle records at
        ``/vehicles/{ship_name}`` where the ship name is passed as a URL path
        parameter.  Returns the ship dict directly, or ``None`` if the ship is
        not found or the API fails.
        """
        endpoint = f"/vehicles/{ship_name}"
        try:
            response = await self._http.get(endpoint)
            response.raise_for_status()

            content_type = response.headers.get("content-type", "")
            if "json" not in content_type:
                log.warning(
                    "Star Citizen Wiki %s returned unexpected content-type %r; body: %.500s",
                    endpoint,
                    content_type,
                    response.text,
                )
                return None

            if not response.text or not response.text.strip():
                log.warning("Star Citizen Wiki %s returned an empty response body", endpoint)
                return None

            payload = response.json()
        except httpx.HTTPError as exc:
            log.warning("Star Citizen Wiki %s request failed for %r: %s", endpoint, ship_name, exc)
            return None
        except Exception as exc:
            log.warning("Star Citizen Wiki unexpected error fetching %r: %s", ship_name, exc)
            return None

        # The API wraps the ship object in {"data": {...}}.
        if isinstance(payload, dict):
            ship_data = payload.get("data") or payload
            if not ship_data:
                log.debug("Star Citizen Wiki: no results for ship %r", ship_name)
                return None
            return ship_data

        log.warning(
            "Star Citizen Wiki %s returned unexpected payload type %s",
            endpoint,
            type(payload).__name__,
        )
        return None

    @staticmethod
    def _extract_hardpoints(ship_data: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
        """Parse raw Wiki ship data into categorised hardpoint buckets.

        The Wiki API does not expose individual hardpoint specs; instead it
        provides summary counts in ``weapon_snapshot``.  This method converts
        those counts into simple bucket entries so the rest of the codebase
        can consume them uniformly.

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

        snapshot: dict[str, Any] = ship_data.get("weapon_snapshot") or {}

        # Weapons: pilot guns + turret guns
        pilot_guns: int = int(snapshot.get("pilot_guns_count") or 0)
        turret_guns: int = int(snapshot.get("turret_weapon_guns_count") or 0)
        total_weapons = pilot_guns + turret_guns
        for _ in range(total_weapons):
            buckets["weapons"].append({"count": 1})

        # Missiles: prefer rack count, fall back to individual missile count
        missile_racks: int = int(snapshot.get("missile_rack_count") or snapshot.get("missile_count") or 0)
        for _ in range(missile_racks):
            buckets["missiles"].append({"count": 1})

        # Shields: 1 slot if the ship has shield HP data
        if ship_data.get("shield_hp"):
            buckets["shields"].append({"count": 1})

        # Power and coolers: assume one of each for any ship
        buckets["power"].append({"count": 1})
        buckets["coolers"].append({"count": 1})

        return buckets

    @staticmethod
    def _extract_performance(ship_data: dict[str, Any]) -> dict[str, Any]:
        """Pull top-level performance metrics out of raw Wiki ship data.

        The Wiki API returns speed data nested under ``speed`` (with ``scm``
        and ``max`` sub-keys), crew data nested under ``crew`` (with ``max``),
        and hull/cargo/shield values at the top level.
        """
        perf: dict[str, Any] = {}

        # Speed — nested under ship_data["speed"]["scm"] / ["max"]
        speed: dict[str, Any] = ship_data.get("speed") or {}
        if speed.get("scm") is not None:
            perf["scm_speed"] = speed["scm"]
        if speed.get("max") is not None:
            perf["max_speed"] = speed["max"]

        # Shields — top-level key
        shield_hp = ship_data.get("shield_hp")
        if shield_hp is not None:
            perf["shield_hp"] = shield_hp

        # Hull HP — top-level "health" key
        hull_hp = ship_data.get("health")
        if hull_hp is not None:
            perf["hull_hp"] = hull_hp

        # Cargo — top-level "cargo_capacity" key
        cargo = ship_data.get("cargo_capacity")
        if cargo is not None:
            perf["cargo_scu"] = cargo

        # Crew — nested under ship_data["crew"]["max"]
        crew: dict[str, Any] = ship_data.get("crew") or {}
        if isinstance(crew, dict) and crew.get("max") is not None:
            perf["max_crew"] = crew["max"]
        elif isinstance(crew, (int, float)):
            perf["max_crew"] = crew

        return perf

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get_ship(self, ship_name: str) -> dict[str, Any] | None:
        """Fetch raw ship data for *ship_name* from the Star Citizen Wiki API.

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

        ship_data = await self._fetch_ship_data(ship_name)
        if ship_data is not None:
            self._ship_detail_cache[key] = (now, ship_data)
        return ship_data

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
