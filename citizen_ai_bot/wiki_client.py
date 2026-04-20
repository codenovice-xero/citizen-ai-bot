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
        parameter.  The ``include=components`` query parameter is added to
        request detailed hardpoint/component data when available.  Returns the
        ship dict directly, or ``None`` if the ship is not found or the API
        fails.
        """
        endpoint = f"/vehicles/{ship_name}"
        try:
            response = await self._http.get(endpoint, params={"include": "components"})
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
            log.debug(
                "Star Citizen Wiki: top-level keys for %r: %s",
                ship_name,
                list(ship_data.keys()) if isinstance(ship_data, dict) else type(ship_data).__name__,
            )
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

        When the API returns detailed component data (via ``include=components``)
        the ``components`` key will contain a list of hardpoint records.  Each
        record is parsed to extract weapon sizes, component names, classes, and
        manufacturer info.  If no detailed component data is present the method
        falls back to the ``weapon_snapshot`` summary counts so the rest of the
        codebase always receives a consistent structure.

        Each bucket entry is a dict that may contain:
        - ``count`` (int): always 1 per entry
        - ``size`` (str | None): e.g. ``"3"`` or ``"S3"``
        - ``component_name`` (str | None): display name of the equipped item
        - ``component_class`` (str | None): e.g. ``"A"``, ``"B"``
        - ``component_type`` (str | None): raw type string from the API, e.g.
          ``"ballistic_cannon"``, ``"laser_repeater"``, ``"weapon_gun"``
        - ``class_name`` (str | None): internal class identifier, e.g. ``"GLSN_Shiv"``
        - ``manufacturer`` (str | None): manufacturer name

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



        # ------------------------------------------------------------------
        # Attempt to parse detailed component data from include=components
        # ------------------------------------------------------------------
        components: list[Any] = ship_data.get("components") or []
        if components and isinstance(components, list):
            # Log the first component's full structure so we can see every
            # available field and identify where the real type name lives.
            first_comp = next((c for c in components if isinstance(c, dict)), None)
            if first_comp is not None:
                log.debug(
                    "Wiki API component keys: %s",
                    list(first_comp.keys()),
                )
                log.debug(
                    "Wiki API first component data: %s",
                    first_comp,
                )

            for comp in components:
                if not isinstance(comp, dict):
                    continue

                # Determine the hardpoint category from the component type/sub_type.
                # comp_type is used purely for bucket routing below.
                comp_type: str = str(comp.get("type") or comp.get("sub_type") or "").lower()

                # Extract the most descriptive type label available.  The API
                # may expose this under several different keys depending on the
                # endpoint version; try them in order of specificity.
                raw_item_type: str | None = (
                    comp.get("item_type")
                    or comp.get("component_type")
                    or comp.get("sub_type")
                    or comp.get("type")
                    or None
                )
                component_type: str | None = (
                    str(raw_item_type).strip() if raw_item_type else None
                )

                comp_name: str | None = comp.get("name") or comp.get("component_name") or None
                comp_class: str | None = comp.get("class") or comp.get("item_class") or None
                comp_size_raw = comp.get("size") or comp.get("item_size") or None
                comp_size: str | None = str(comp_size_raw) if comp_size_raw is not None else None
                manufacturer: str | None = (
                    comp.get("manufacturer")
                    or (comp.get("manufacturer_data") or {}).get("name")
                    or None
                )
                class_name: str | None = comp.get("class_name") or None

                entry: dict[str, Any] = {
                    "count": 1,
                    "size": comp_size,
                    "component_name": comp_name,
                    "component_class": comp_class,
                    "component_type": component_type,
                    "class_name": class_name,
                    "manufacturer": manufacturer,
                }


                if any(kw in comp_type for kw in ("weapon", "gun", "laser", "cannon", "repeater", "ballistic")):
                    buckets["weapons"].append(entry)
                elif any(kw in comp_type for kw in ("missile", "torpedo", "rack")):
                    buckets["missiles"].append(entry)
                elif any(kw in comp_type for kw in ("shield",)):
                    buckets["shields"].append(entry)
                elif any(kw in comp_type for kw in ("power", "powerplant", "power_plant")):
                    buckets["power"].append(entry)
                elif any(kw in comp_type for kw in ("cooler",)):
                    buckets["coolers"].append(entry)
                else:
                    buckets["other"].append(entry)

            # If we successfully parsed at least one component, return early.
            # Fill in any empty shield/power/cooler slots from snapshot data so
            # the display is never completely blank for those categories.
            if any(buckets[k] for k in ("weapons", "missiles", "shields", "power", "coolers")):
                if not buckets["shields"] and ship_data.get("shield_hp"):
                    buckets["shields"].append({"count": 1, "size": None, "component_name": None,
                                               "component_class": None, "manufacturer": None})
                if not buckets["power"]:
                    buckets["power"].append({"count": 1, "size": None, "component_name": None,
                                             "component_class": None, "manufacturer": None})
                if not buckets["coolers"]:
                    buckets["coolers"].append({"count": 1, "size": None, "component_name": None,
                                               "component_class": None, "manufacturer": None})
                return buckets

        # ------------------------------------------------------------------
        # Fallback: use weapon_snapshot summary counts
        # ------------------------------------------------------------------
        snapshot: dict[str, Any] = ship_data.get("weapon_snapshot") or {}

        # Weapons: pilot guns + turret guns
        pilot_guns: int = int(snapshot.get("pilot_guns_count") or 0)
        turret_guns: int = int(snapshot.get("turret_weapon_guns_count") or 0)
        total_weapons = pilot_guns + turret_guns
        for _ in range(total_weapons):
            buckets["weapons"].append({"count": 1, "size": None, "component_name": None,
                                       "component_class": None, "manufacturer": None})

        # Missiles: prefer rack count, fall back to individual missile count
        missile_racks: int = int(snapshot.get("missile_rack_count") or snapshot.get("missile_count") or 0)
        for _ in range(missile_racks):
            buckets["missiles"].append({"count": 1, "size": None, "component_name": None,
                                        "component_class": None, "manufacturer": None})

        # Shields: 1 slot if the ship has shield HP data
        if ship_data.get("shield_hp"):
            buckets["shields"].append({"count": 1, "size": None, "component_name": None,
                                       "component_class": None, "manufacturer": None})

        # Power and coolers: assume one of each for any ship
        buckets["power"].append({"count": 1, "size": None, "component_name": None,
                                 "component_class": None, "manufacturer": None})
        buckets["coolers"].append({"count": 1, "size": None, "component_name": None,
                                   "component_class": None, "manufacturer": None})

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
