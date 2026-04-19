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

        The Star Citizen Wiki API supports querying ships by name directly via
        the ``/ships`` endpoint with a ``query`` parameter.  Returns the first
        matching result, or ``None`` if nothing is found or the API fails.
        """
        try:
            response = await self._http.get(
                "/ships",
                params={"query": ship_name, "limit": 5},
            )
            response.raise_for_status()

            content_type = response.headers.get("content-type", "")
            if "json" not in content_type:
                log.warning(
                    "Star Citizen Wiki /ships returned unexpected content-type %r; body: %.500s",
                    content_type,
                    response.text,
                )
                return None

            if not response.text or not response.text.strip():
                log.warning("Star Citizen Wiki /ships returned an empty response body")
                return None

            payload = response.json()
        except httpx.HTTPError as exc:
            log.warning("Star Citizen Wiki /ships request failed for %r: %s", ship_name, exc)
            return None
        except Exception as exc:
            log.warning("Star Citizen Wiki unexpected error fetching %r: %s", ship_name, exc)
            return None

        # The Wiki API wraps results in a "data" key containing a list.
        if isinstance(payload, dict):
            data = payload.get("data") or []
        elif isinstance(payload, list):
            data = payload
        else:
            log.warning(
                "Star Citizen Wiki /ships returned unexpected payload type %s",
                type(payload).__name__,
            )
            return None

        if not data:
            log.debug("Star Citizen Wiki: no results for ship %r", ship_name)
            return None

        target = _norm_ship_name(ship_name)

        # Prefer an exact normalised name match; fall back to the first result.
        for entry in data:
            if not isinstance(entry, dict):
                continue
            candidate = _norm_ship_name(str(entry.get("name") or ""))
            if candidate == target:
                return entry

        first = data[0] if isinstance(data[0], dict) else None
        return first

    @staticmethod
    def _extract_hardpoints(ship_data: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
        """Parse raw Wiki ship data into categorised hardpoint buckets.

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

        # The Wiki API may expose hardpoints under several keys.
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
                hp.get("type") or hp.get("category") or hp.get("item_type") or ""
            ).lower()
            component = hp.get("component") or hp.get("item") or {}
            if isinstance(component, str):
                component = {"name": component}

            entry: dict[str, Any] = {
                "slot": hp.get("slot") or hp.get("name") or hp.get("hardpoint_name"),
                "size": hp.get("size") or hp.get("max_size") or component.get("size"),
                "component_name": component.get("name") or component.get("item_name"),
                "component_class": component.get("class") or component.get("grade"),
                "manufacturer": component.get("manufacturer") or component.get("brand"),
                "raw": hp,
            }

            if any(kw in hp_type for kw in ("weapon", "gun", "cannon", "laser", "ballistic", "repeater")):
                buckets["weapons"].append(entry)
            elif "shield" in hp_type:
                buckets["shields"].append(entry)
            elif any(kw in hp_type for kw in ("power", "powerplant", "qig")):
                buckets["power"].append(entry)
            elif "cooler" in hp_type:
                buckets["coolers"].append(entry)
            elif any(kw in hp_type for kw in ("missile", "rocket", "torpedo")):
                buckets["missiles"].append(entry)
            else:
                buckets["other"].append(entry)

        return buckets

    @staticmethod
    def _extract_performance(ship_data: dict[str, Any]) -> dict[str, Any]:
        """Pull top-level performance metrics out of raw Wiki ship data."""
        perf: dict[str, Any] = {}

        # Speed / flight — Wiki API uses snake_case keys.
        for key in ("scm_speed", "scmSpeed", "max_speed", "maxSpeed", "afterburner_speed", "afterburnerSpeed"):
            val = ship_data.get(key)
            if val is not None:
                if "scm" in key.lower():
                    perf.setdefault("scm_speed", val)
                else:
                    perf.setdefault("max_speed", val)

        # Shields
        for key in ("shield_hp", "shieldHp", "shield_health", "shieldHealth"):
            val = ship_data.get(key)
            if val is not None:
                perf["shield_hp"] = val
                break

        # Hull
        for key in ("hull_hp", "hullHp", "hull_health", "hullHealth"):
            val = ship_data.get(key)
            if val is not None:
                perf["hull_hp"] = val
                break

        # Cargo
        for key in ("cargo_capacity", "cargoCapacity", "cargo", "scu"):
            val = ship_data.get(key)
            if val is not None:
                perf["cargo_scu"] = val
                break

        # Crew
        for key in ("max_crew", "maxCrew", "crew_size", "crewSize", "crew"):
            val = ship_data.get(key)
            if val is not None:
                perf["max_crew"] = val
                break

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
