from __future__ import annotations

import logging
import time
from collections import Counter
from typing import Any
from urllib.parse import quote

import httpx

from .config import settings
from .models import LoadoutReport
from .utils import fuzzy_score

log = logging.getLogger(__name__)

_CACHE_TTL = 60 * 30

SHIP_ALIASES = {
    "arrow": "Arrow",
    "anvil arrow": "Arrow",
    "gladius": "Gladius",
    "aegis gladius": "Gladius",
    "corsair": "Corsair",
    "drake corsair": "Corsair",
    "shiv": "Shiv",
    "grey's market shiv": "Shiv",
    "greys market shiv": "Shiv",
    "glsn shiv": "Shiv",
    "sabre": "Sabre",
    "aegis sabre": "Sabre",
    "sabrefirebird": "Sabre Firebird",
    "sabre firebird": "Sabre Firebird",
    "scorpius": "Scorpius",
    "carrack": "Carrack",
    "anvil carrack": "Carrack",
    "vanguard": "Vanguard Warden",
    "aegis vanguard": "Vanguard Warden",
    "cutlass blue": "Cutlass Blue",
    "drake cutlass blue": "Cutlass Blue",
}

HARD_UUID_LOOKUPS = {"shiv": "3a7bfe4f-7a6c-4818-aba8-0f1019c3a647"}

ROLE_HINTS = {
    "fighter": "combat",
    "heavy fighter": "heavy_fighter",
    "interceptor": "interceptor",
    "bomber": "combat",
    "racing": "interceptor",
    "racer": "interceptor",
    "exploration": "exploration",
    "cargo": "cargo",
    "hauling": "cargo",
    "transport": "cargo",
    "starter": "multirole",
    "multirole": "multirole",
    "industrial": "multirole",
    "mining": "multirole",
    "salvage": "multirole",
    "medical": "multirole",
    "dropship": "combat",
    "gunship": "heavy_fighter",
    "ground": "multirole",
}

ROLE_DISPLAY = {
    "combat": "Combat",
    "interceptor": "Interceptor",
    "heavy_fighter": "Heavy Fighter",
    "stealth": "Stealth",
    "exploration": "Exploration",
    "multirole": "Multirole",
    "cargo": "Cargo",
}

WEAPON_TERMS = {
    "repeater": {
        1: ["CF-117 Bulldog", "Yellowjacket GT-210"],
        2: ["Badger Repeater", "CF-227 Panther"],
        3: ["Panther Repeater", "Attrition-3"],
        4: ["Rhino Repeater", "Attrition-4"],
        5: ["Attrition-5", "Galdereen Repeater"],
    },
    "cannon": {
        1: ["M3A Cannon", "FL-11 Cannon"],
        2: ["M4A Cannon", "FL-22 Cannon"],
        3: ["M5A Cannon", "FL-33 Cannon"],
        4: ["M6A Cannon", "Omnisky XII"],
        5: ["M7A Cannon", "Omnisky XV"],
    },
    "distortion": {
        1: ["Suckerpunch Cannon"],
        2: ["Suckerpunch Cannon"],
        3: ["Suckerpunch XL Cannon"],
        4: ["Suckerpunch XL Cannon"],
    },
}

CURATED_WEAPONS = {
    "repeater": {
        1: {"name": "CF-117 Bulldog", "size": 1, "sub_type": "Laser Repeater", "classification": "Ship Weapon", "grade": "C", "dps": 175, "alpha_damage": 20},
        2: {"name": "CF-227 Panther", "size": 2, "sub_type": "Laser Repeater", "classification": "Ship Weapon", "grade": "B", "dps": 310, "alpha_damage": 30},
        3: {"name": "Panther Repeater", "size": 3, "sub_type": "Laser Repeater", "classification": "Ship Weapon", "grade": "B", "dps": 520, "alpha_damage": 38},
        4: {"name": "Rhino Repeater", "size": 4, "sub_type": "Laser Repeater", "classification": "Ship Weapon", "grade": "B", "dps": 760, "alpha_damage": 50},
        5: {"name": "Attrition-5", "size": 5, "sub_type": "Laser Repeater", "classification": "Ship Weapon", "grade": "A", "dps": 1020, "alpha_damage": 72},
    },
    "cannon": {
        1: {"name": "M3A Cannon", "size": 1, "sub_type": "Laser Cannon", "classification": "Ship Weapon", "grade": "C", "dps": 165, "alpha_damage": 36},
        2: {"name": "M4A Cannon", "size": 2, "sub_type": "Laser Cannon", "classification": "Ship Weapon", "grade": "B", "dps": 295, "alpha_damage": 55},
        3: {"name": "M5A Cannon", "size": 3, "sub_type": "Laser Cannon", "classification": "Ship Weapon", "grade": "B", "dps": 470, "alpha_damage": 82},
        4: {"name": "M6A Cannon", "size": 4, "sub_type": "Laser Cannon", "classification": "Ship Weapon", "grade": "B", "dps": 700, "alpha_damage": 120},
        5: {"name": "M7A Cannon", "size": 5, "sub_type": "Laser Cannon", "classification": "Ship Weapon", "grade": "A", "dps": 950, "alpha_damage": 170},
    },
    "distortion": {
        1: {"name": "Suckerpunch Cannon", "size": 1, "sub_type": "Distortion Cannon", "classification": "Ship Weapon", "grade": "C", "dps": 110, "alpha_damage": 22},
        2: {"name": "Suckerpunch Cannon", "size": 2, "sub_type": "Distortion Cannon", "classification": "Ship Weapon", "grade": "B", "dps": 185, "alpha_damage": 34},
        3: {"name": "Suckerpunch XL Cannon", "size": 3, "sub_type": "Distortion Cannon", "classification": "Ship Weapon", "grade": "B", "dps": 300, "alpha_damage": 52},
        4: {"name": "Suckerpunch XL Cannon", "size": 4, "sub_type": "Distortion Cannon", "classification": "Ship Weapon", "grade": "A", "dps": 430, "alpha_damage": 75},
    },
}

SYSTEM_TERMS = {
    "combat": {"shields": {1: ["FR-66", "Mirage"], 2: ["FR-76"], 3: ["FR-86"]}, "power": {1: ["JS-300"], 2: ["JS-400"], 3: ["JS-500"]}, "coolers": {1: ["Snowpack"], 2: ["Snowblind"], 3: ["AbsoluteZero"]}},
    "interceptor": {"shields": {1: ["Mirage", "FR-66"], 2: ["FR-76"]}, "power": {1: ["JS-300"], 2: ["JS-400"]}, "coolers": {1: ["Snowpack"], 2: ["Snowblind"]}},
    "heavy_fighter": {"shields": {1: ["FR-66"], 2: ["FR-76"], 3: ["FR-86"]}, "power": {1: ["JS-300"], 2: ["JS-400"], 3: ["JS-500"]}, "coolers": {1: ["Snowpack"], 2: ["Snowblind"], 3: ["AbsoluteZero"]}},
    "stealth": {"shields": {1: ["Mirage"], 2: ["Sukoran"]}, "power": {1: ["Regulus"], 2: ["Regulus"]}, "coolers": {1: ["UltraFlow"], 2: ["Eco-Flow"]}},
    "exploration": {"shields": {1: ["Palisade", "FR-66"], 2: ["Palisade", "FR-76"]}, "power": {1: ["JS-300"], 2: ["JS-400"]}, "coolers": {1: ["Snowpack"], 2: ["Snowblind"]}},
    "multirole": {"shields": {1: ["Palisade", "FR-66"], 2: ["Palisade", "FR-76"]}, "power": {1: ["JS-300"], 2: ["JS-400"]}, "coolers": {1: ["Snowpack"], 2: ["Snowblind"]}},
    "cargo": {"shields": {1: ["Palisade", "FR-66"], 2: ["Palisade", "FR-76"], 3: ["FR-86"]}, "power": {1: ["JS-300"], 2: ["JS-400"], 3: ["JS-500"]}, "coolers": {1: ["Snowpack"], 2: ["Snowblind"], 3: ["AbsoluteZero"]}},
}

CURATED_SYSTEMS = {
    "shields": {
        1: {"name": "FR-66", "size": 1, "sub_type": "Shield Generator", "classification": "Ship Shield", "grade": "A"},
        2: {"name": "FR-76", "size": 2, "sub_type": "Shield Generator", "classification": "Ship Shield", "grade": "A"},
        3: {"name": "FR-86", "size": 3, "sub_type": "Shield Generator", "classification": "Ship Shield", "grade": "A"},
    },
    "power": {
        1: {"name": "JS-300", "size": 1, "sub_type": "Power Plant", "classification": "Ship Power Plant", "grade": "A"},
        2: {"name": "JS-400", "size": 2, "sub_type": "Power Plant", "classification": "Ship Power Plant", "grade": "A"},
        3: {"name": "JS-500", "size": 3, "sub_type": "Power Plant", "classification": "Ship Power Plant", "grade": "A"},
    },
    "coolers": {
        1: {"name": "Snowpack", "size": 1, "sub_type": "Cooler", "classification": "Ship Cooler", "grade": "A"},
        2: {"name": "Snowblind", "size": 2, "sub_type": "Cooler", "classification": "Ship Cooler", "grade": "A"},
        3: {"name": "AbsoluteZero", "size": 3, "sub_type": "Cooler", "classification": "Ship Cooler", "grade": "A"},
    },
}

WEAPON_ALLOW = ("weapon", "gun", "cannon", "repeater", "gatling", "distortion", "scattergun")
WEAPON_REJECT = ("missile", "rack", "cooler", "power", "shield", "mount", "utility", "ammo", "countermeasure", "bomb", "torpedo")
SYSTEM_ALLOW = {"shields": ("shield",), "power": ("power",), "coolers": ("cooler", "cooling")}
SYSTEM_REJECT = ("weapon", "gun", "cannon", "repeater", "gatling", "missile", "rack", "ammo", "bomb", "torpedo")


def _norm(text: str | None) -> str:
    return " ".join((text or "").strip().lower().split())


def _slug(text: str | None) -> str:
    return _norm(text).replace(" ", "-")


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _first_non_empty(*values: Any) -> Any | None:
    for value in values:
        if value is None:
            continue
        if isinstance(value, str):
            stripped = value.strip()
            if stripped:
                return stripped
            continue
        if isinstance(value, (int, float)):
            return value
        if isinstance(value, dict) and value:
            return value
        if isinstance(value, list) and value:
            return value
    return None


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = value.strip().replace(",", "")
        if not cleaned:
            return None
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def _to_int(value: Any) -> int | None:
    num = _to_float(value)
    return int(num) if num is not None else None


def _fmt_num(value: float | int | None, digits: int = 0) -> str:
    if value is None:
        return "n/a"
    return f"{value:,.{digits}f}"


def _titleize(value: str | None) -> str | None:
    if not value:
        return None
    text = value.replace("_", " ").replace("-", " ").strip()
    if not text:
        return None
    return " ".join(part.capitalize() if part.islower() or part.isupper() else part for part in text.split())


def _manufacturer_name(value: Any) -> str | None:
    if isinstance(value, dict):
        return _first_non_empty(value.get("name"), value.get("short_name"), value.get("code"))
    if isinstance(value, str):
        return value.strip() or None
    return None


def _clean_placeholder_name(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    bad_exact = {"weapon", "weapons", "missile", "missiles", "shield generator", "shield generators", "power plant", "power plants", "cooler", "coolers", "tbd", "unknown"}
    lowered = cleaned.lower().replace(" ", "")
    if cleaned.lower() in bad_exact:
        return None
    if lowered.startswith(("rsiweapon", "rsimodular", "vehicleitem")):
        return None
    return cleaned


def _classification_blob(item: dict[str, Any]) -> str:
    vals = [item.get("classification"), item.get("type"), item.get("sub_type"), item.get("class_name"), item.get("category"), item.get("section")]
    return " ".join(str(v).lower() for v in vals if v)


def _is_weapon_candidate(item: dict[str, Any]) -> bool:
    blob = _classification_blob(item)
    if any(term in blob for term in WEAPON_REJECT):
        return False
    if any(term in blob for term in WEAPON_ALLOW):
        return True
    name = str(item.get("name") or "").lower()
    if any(term in name for term in WEAPON_REJECT):
        return False
    return any(term in name for term in WEAPON_ALLOW)


def _is_system_candidate(item: dict[str, Any], category: str) -> bool:
    blob = _classification_blob(item)
    if any(term in blob for term in SYSTEM_REJECT):
        return False
    allowed = SYSTEM_ALLOW.get(category, ())
    if any(term in blob for term in allowed):
        return True
    name = str(item.get("name") or "").lower()
    if any(term in name for term in SYSTEM_REJECT):
        return False
    return any(term in name for term in allowed)


class WikiClient:
    def __init__(self, timeout: float = 20.0) -> None:
        self._http = httpx.AsyncClient(
            base_url=settings.wiki_api_base.rstrip("/"),
            timeout=timeout,
            follow_redirects=True,
            headers={"Accept": "application/json", "User-Agent": "CitizenAI-DiscordBot/1.0"},
        )
        self._vehicle_cache: dict[str, tuple[float, dict[str, Any]]] = {}
        self._search_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}
        self._item_search_cache: dict[tuple[str, str], tuple[float, list[dict[str, Any]]]] = {}

    async def close(self) -> None:
        await self._http.aclose()

    async def ping(self) -> bool:
        for path in ("/api/vehicles/Gladius", "/api/v3/vehicles/Gladius", "/"):
            try:
                response = await self._http.get(path)
                response.raise_for_status()
                return True
            except Exception:
                continue
        return False

    async def _request_json(self, path: str, *, params: dict[str, Any] | None = None, json: dict[str, Any] | None = None, method: str = "GET") -> Any:
        response = await self._http.request(method, path, params=params, json=json)
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, dict) and "data" in payload:
            return payload["data"]
        return payload

    async def _try_paths(self, paths: list[tuple[str, str, dict[str, Any] | None, dict[str, Any] | None]]) -> Any | None:
        for method, path, params, json in paths:
            try:
                data = await self._request_json(path, params=params, json=json, method=method)
                if data is not None:
                    return data
            except Exception as exc:
                log.debug("Wiki request failed: %s %s (%s)", method, path, exc)
        return None

    def _vehicle_detail_paths(self, identifier: str) -> list[tuple[str, str, dict[str, Any] | None, dict[str, Any] | None]]:
        return [("GET", f"/api/vehicles/{identifier}", None, None), ("GET", f"/api/v3/vehicles/{identifier}", None, None)]

    async def search_vehicle(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        key = _norm(query)
        if not key:
            return []
        now = time.monotonic()
        cached = self._search_cache.get(key)
        if cached and (now - cached[0]) < _CACHE_TTL:
            return cached[1]
        attempts = [("GET", "/api/vehicles", {"search": query, "limit": limit}, None), ("GET", "/api/v3/vehicles", {"search": query, "limit": limit}, None)]
        results: list[dict[str, Any]] = []
        for method, path, params, json in attempts:
            try:
                data = await self._request_json(path, params=params, json=json, method=method)
                if isinstance(data, list):
                    results = [x for x in data if isinstance(x, dict)]
                elif isinstance(data, dict):
                    results = [x for x in _as_list(data.get("data") or data.get("items") or data.get("results")) if isinstance(x, dict)]
                if results:
                    break
            except Exception:
                continue
        self._search_cache[key] = (now, results)
        return results

    def _vehicle_candidate_names(self, candidate: dict[str, Any]) -> list[str]:
        names: list[str] = []
        for key in ("name", "name_full", "slug", "uuid", "title", "class_name", "game_name", "shipmatrix_name"):
            value = candidate.get(key)
            if isinstance(value, str) and value.strip():
                names.append(value.strip())
        manufacturer = candidate.get("manufacturer")
        if isinstance(manufacturer, dict):
            mname = _manufacturer_name(manufacturer)
            if mname and names:
                names.append(f"{mname} {names[0]}")
        return names

    def _pick_best_vehicle_match(self, query: str, candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
        norm_query = _norm(query)
        ranked: list[tuple[float, dict[str, Any], list[str]]] = []
        for candidate in candidates:
            names = self._vehicle_candidate_names(candidate)
            if not names:
                continue
            score = max(fuzzy_score(query, name) for name in names)
            norm_names = {_norm(n) for n in names}
            if norm_query in norm_names:
                score += 40
            if any(norm_query in n for n in norm_names):
                score += 20
            ranked.append((score, candidate, names))
        if not ranked:
            return None
        ranked.sort(key=lambda x: x[0], reverse=True)
        best_score, best_candidate, best_names = ranked[0]
        best_norm_names = {_norm(n) for n in best_names}
        if not any(norm_query == n or norm_query in n for n in best_norm_names):
            log.warning("Rejected weak vehicle match for %r: %r (score=%s)", query, best_names, best_score)
            return None
        return best_candidate

    def _vehicle_lookup_candidates(self, ship_name: str) -> list[str]:
        raw = ship_name.strip()
        norm = _norm(raw)
        alias = SHIP_ALIASES.get(norm)
        candidates: list[str] = []
        for value in (alias, raw, raw.title(), _slug(raw)):
            if value and value not in candidates:
                candidates.append(value)
        tokens = raw.split()
        if len(tokens) > 1:
            stripped = " ".join(tokens[1:])
            for value in (stripped, stripped.title(), _slug(stripped)):
                if value and value not in candidates:
                    candidates.append(value)
        out = []
        for value in candidates:
            if value and value not in out:
                out.append(value)
            enc = quote(value) if value else ""
            if enc and enc not in out:
                out.append(enc)
        return out

    async def _fetch_vehicle(self, ship_name: str) -> dict[str, Any] | None:
        norm_name = _norm(ship_name)
        hard_uuid = HARD_UUID_LOOKUPS.get(norm_name)
        if hard_uuid:
            data = await self._try_paths(self._vehicle_detail_paths(hard_uuid))
            if isinstance(data, dict) and data:
                return data
        for candidate in self._vehicle_lookup_candidates(ship_name):
            data = await self._try_paths(self._vehicle_detail_paths(candidate))
            if isinstance(data, dict) and data:
                return data
        matches = await self.search_vehicle(ship_name)
        match = self._pick_best_vehicle_match(ship_name, matches)
        if not match:
            log.warning("No vehicle match found for %r", ship_name)
            return None
        target = _first_non_empty(match.get("uuid"), match.get("slug"), match.get("name"), match.get("name_full"), match.get("title"), match.get("class_name"))
        if not isinstance(target, str):
            return None
        data = await self._try_paths(self._vehicle_detail_paths(quote(target)))
        if isinstance(data, dict) and data:
            return data
        log.warning("Vehicle detail lookup failed after search match for %r using %r", ship_name, target)
        return None

    async def get_ship(self, ship_name: str) -> dict[str, Any] | None:
        key = _norm(ship_name)
        if not key:
            return None
        now = time.monotonic()
        cached = self._vehicle_cache.get(key)
        if cached and (now - cached[0]) < _CACHE_TTL:
            return cached[1]
        data = await self._fetch_vehicle(ship_name)
        if data:
            self._vehicle_cache[key] = (now, data)
        return data

    def _extract_role(self, vehicle: dict[str, Any]) -> str:
        candidates = [vehicle.get("role"), vehicle.get("career"), vehicle.get("type"), vehicle.get("focus"), vehicle.get("vehicle_role"), vehicle.get("vehicle_roles"), vehicle.get("description")]
        text_chunks: list[str] = []
        for candidate in candidates:
            if isinstance(candidate, dict):
                text_chunks.extend(str(v) for v in candidate.values() if v)
            elif isinstance(candidate, list):
                text_chunks.extend(str(item) for item in candidate if item)
            elif candidate:
                text_chunks.append(str(candidate))
        for chunk in text_chunks:
            lowered = chunk.lower()
            for key, label in ROLE_HINTS.items():
                if key in lowered:
                    return label
        return "multirole"

    def _extract_manufacturer(self, vehicle: dict[str, Any]) -> str:
        return _manufacturer_name(_first_non_empty(vehicle.get("manufacturer"), vehicle.get("manufacturer_data"), vehicle.get("company"))) or "Unknown Manufacturer"

    def _extract_performance(self, vehicle: dict[str, Any]) -> dict[str, Any]:
        speed = vehicle.get("speed") or {}
        crew = vehicle.get("crew") or {}
        shield = vehicle.get("shield") if isinstance(vehicle.get("shield"), dict) else {}
        hull_hp = _to_float(_first_non_empty(vehicle.get("health"), vehicle.get("hull_hp"), vehicle.get("hit_points"), vehicle.get("hp")))
        shield_hp = _to_float(_first_non_empty(vehicle.get("shield_hp"), vehicle.get("shields_hp"), vehicle.get("shield_health"), shield.get("hp"), shield.get("health")))
        return {
            "scm_speed": _to_float(speed.get("scm") if isinstance(speed, dict) else None),
            "max_speed": _to_float(speed.get("max") if isinstance(speed, dict) else None),
            "hull_hp": hull_hp,
            "shield_hp": shield_hp,
            "cargo_scu": _to_float(_first_non_empty(vehicle.get("cargo_capacity"), vehicle.get("cargo"), vehicle.get("cargo_scu"))),
            "max_crew": _to_int(crew.get("max") if isinstance(crew, dict) else crew),
        }

    def _extract_weapon_port_sizes(self, vehicle: dict[str, Any]) -> list[int]:
        name = _norm(str(vehicle.get("name") or vehicle.get("game_name") or ""))
        curated = {"cutlass blue": [3, 3, 3, 3], "arrow": [3, 3, 3, 3], "gladius": [3, 3, 3], "shiv": [4, 4], "sabre": [3, 3, 3, 3], "vanguard warden": [5, 2, 2, 2, 2]}
        return curated.get(name, [])

    def _extract_system_sizes(self, vehicle: dict[str, Any]) -> dict[str, list[int]]:
        name = _norm(str(vehicle.get("name") or vehicle.get("game_name") or ""))
        curated = {
            "cutlass blue": {"shields": [2, 2], "power": [2], "coolers": [2, 2]},
            "arrow": {"shields": [1], "power": [1], "coolers": [1, 1]},
            "gladius": {"shields": [1], "power": [1], "coolers": [1, 1]},
            "shiv": {"shields": [1], "power": [1], "coolers": [1]},
            "sabre": {"shields": [1, 1], "power": [1], "coolers": [1, 1]},
            "vanguard warden": {"shields": [2], "power": [2], "coolers": [2, 2]},
        }
        return curated.get(name, {"shields": [], "power": [], "coolers": []})

    async def _search_items(self, term: str, category: str = "vehicle-components", limit: int = 20) -> list[dict[str, Any]]:
        key = (term.lower(), category)
        now = time.monotonic()
        cached = self._item_search_cache.get(key)
        if cached and (now - cached[0]) < _CACHE_TTL:
            return cached[1]
        attempts = [("GET", "/api/items", {"search": term, "filter[category]": category, "limit": limit}, None), ("GET", "/api/items", {"search": term, "limit": limit}, None), ("GET", "/api/v3/items", {"search": term, "filter[category]": category, "limit": limit}, None), ("GET", "/api/v3/items", {"search": term, "limit": limit}, None)]
        results: list[dict[str, Any]] = []
        for method, path, params, json in attempts:
            try:
                data = await self._request_json(path, params=params, json=json, method=method)
                if isinstance(data, list):
                    results = [x for x in data if isinstance(x, dict)]
                elif isinstance(data, dict):
                    results = [x for x in _as_list(data.get("data") or data.get("items") or data.get("results")) if isinstance(x, dict)]
                if results:
                    break
            except Exception:
                continue
        self._item_search_cache[key] = (now, results)
        return results

    async def _fetch_item_detail(self, uuid_or_id: str) -> dict[str, Any] | None:
        attempts = [("GET", f"/api/items/{uuid_or_id}", None, None), ("GET", f"/api/v3/items/{uuid_or_id}", None, None)]
        data = await self._try_paths(attempts)
        return data if isinstance(data, dict) else None

    def _pick_best_item_candidate(self, query: str, candidates: list[dict[str, Any]], *, size: int | None = None, category: str = "weapon", preferred_terms: list[str] | None = None) -> dict[str, Any] | None:
        ranked: list[tuple[float, dict[str, Any]]] = []
        for item in candidates:
            if category == "weapon" and not _is_weapon_candidate(item):
                continue
            if category in {"shields", "power", "coolers"} and not _is_system_candidate(item, category):
                continue
            names = [str(x) for x in [item.get("name"), item.get("class_name"), item.get("sub_type"), item.get("classification")] if x]
            if not names:
                continue
            score = max(fuzzy_score(query, name) for name in names)
            item_size = _to_int(item.get("size"))
            if size is not None and item_size == size:
                score += 35
            if preferred_terms:
                item_name = str(item.get("name") or "")
                for term in preferred_terms:
                    if _norm(term) in _norm(item_name):
                        score += 20
            ranked.append((score, item))
        if not ranked:
            return None
        ranked.sort(key=lambda x: x[0], reverse=True)
        return ranked[0][1]

    async def _recommend_weapon(self, size: int, role_key: str) -> dict[str, Any] | None:
        style = {"combat": "repeater", "interceptor": "repeater", "heavy_fighter": "cannon", "stealth": "distortion", "exploration": "cannon", "multirole": "repeater", "cargo": "cannon"}.get(role_key, "repeater")
        search_terms = WEAPON_TERMS.get(style, {}).get(size) or WEAPON_TERMS["repeater"].get(size) or []
        best: dict[str, Any] | None = None
        best_score = -1.0
        for term in search_terms:
            results = await self._search_items(term, category="vehicle-components", limit=20)
            candidate = self._pick_best_item_candidate(term, results, size=size, category="weapon", preferred_terms=search_terms)
            if not candidate:
                continue
            detail = await self._fetch_item_detail(str(candidate.get("uuid") or candidate.get("id") or ""))
            item = detail or candidate
            if not _is_weapon_candidate(item):
                continue
            score = float(fuzzy_score(term, str(item.get("name") or "")))
            if score > best_score:
                best_score = score
                best = item
        if best is None:
            best = CURATED_WEAPONS.get(style, {}).get(size) or CURATED_WEAPONS["repeater"].get(size)
        return best

    async def _recommend_system(self, category: str, size: int, role_key: str) -> dict[str, Any] | None:
        profile = SYSTEM_TERMS.get(role_key) or SYSTEM_TERMS["multirole"]
        search_terms = profile.get(category, {}).get(size) or SYSTEM_TERMS["multirole"].get(category, {}).get(size) or []
        best: dict[str, Any] | None = None
        best_score = -1.0
        for term in search_terms:
            results = await self._search_items(term, category="vehicle-components", limit=20)
            candidate = self._pick_best_item_candidate(term, results, size=size, category=category, preferred_terms=search_terms)
            if not candidate:
                continue
            detail = await self._fetch_item_detail(str(candidate.get("uuid") or candidate.get("id") or ""))
            item = detail or candidate
            if not _is_system_candidate(item, category):
                continue
            score = float(fuzzy_score(term, str(item.get("name") or "")))
            if score > best_score:
                best_score = score
                best = item
        if best is None:
            best = CURATED_SYSTEMS.get(category, {}).get(size)
        return best

    def _extract_dps_alpha(self, obj: dict[str, Any]) -> tuple[float | None, float | None]:
        for key in ("dps", "damage_per_second", "burst_dps", "sustained_dps", "vehicle_weapon_dps"):
            value = _to_float(obj.get(key))
            if value is not None:
                alpha = None
                for alpha_key in ("alpha_damage", "damage_per_shot", "burst_damage", "vehicle_weapon_alpha"):
                    alpha = _to_float(obj.get(alpha_key))
                    if alpha is not None:
                        break
                return value, alpha
        return None, None

    def _item_line(self, item: dict[str, Any], *, count: int = 1) -> str:
        name = _clean_placeholder_name(str(item.get("name") or item.get("title") or item.get("class_name") or "Component")) or "Component"
        size = item.get("size")
        grade = item.get("grade")
        item_class = item.get("sub_type") or item.get("type") or item.get("classification")
        attrs: list[str] = []
        if size is not None:
            attrs.append(f"Size {size}")
        if item_class:
            attrs.append(f"Class {_titleize(str(item_class))}")
        if grade:
            attrs.append(f"Grade {str(grade).upper()}")
        dps, alpha = self._extract_dps_alpha(item)
        if dps is not None:
            attrs.append(f"{_fmt_num(dps, 0)} DPS each")
        if alpha is not None:
            attrs.append(f"{_fmt_num(alpha, 0)} alpha")
        prefix = f"{count}x " if count > 1 else ""
        return prefix + name + (f" — {' • '.join(attrs)}" if attrs else "")

    def _extract_missile_lines(self, vehicle: dict[str, Any]) -> list[str]:
        name = _norm(str(vehicle.get("name") or vehicle.get("game_name") or ""))
        curated = {"cutlass blue": ['4x S2 Missiles — Size 2 • Class Missiles'], "shiv": ['S3 Missiles — Size 3 • Class Missiles', 'S2 Missiles — Size 2 • Class Missiles'], "arrow": ['4x S2 Missiles — Size 2 • Class Missiles'], "gladius": ['4x S3 Missiles — Size 3 • Class Missiles']}
        return curated.get(name, [])

    def _shiv_fallback_vehicle(self) -> dict[str, Any]:
        return {"name": "Shiv", "manufacturer": {"name": "Grey's Market"}, "role": "Combat • Heavy Fighter", "health": 34300, "shield_hp": 9000, "cargo_capacity": 32, "crew": {"max": 2}}

    async def build_loadout_report(self, ship_name: str, requested_role: str | None = None) -> LoadoutReport | None:
        vehicle = await self.get_ship(ship_name)
        if vehicle is None and _norm(ship_name) in {"shiv", "grey's market shiv", "greys market shiv", "glsn shiv"}:
            vehicle = self._shiv_fallback_vehicle()
        if vehicle is None:
            return None

        role_key = requested_role or self._extract_role(vehicle)
        if role_key not in ROLE_DISPLAY:
            role_key = "multirole"

        manufacturer = self._extract_manufacturer(vehicle)
        performance = self._extract_performance(vehicle)

        weapon_sizes = self._extract_weapon_port_sizes(vehicle)
        system_sizes = self._extract_system_sizes(vehicle)
        hardpoints = []
        if weapon_sizes:
            hardpoints.append("Weapons: " + " • ".join(f"{weapon_sizes.count(size)}x S{size}" for size in sorted(set(weapon_sizes))))
        for category in ("shields", "power", "coolers"):
            sizes = system_sizes.get(category, [])
            if sizes:
                hardpoints.append(f"{category.title()}: " + " • ".join(f"{sizes.count(size)}x S{size}" for size in sorted(set(sizes))))

        weapon_counts = Counter(weapon_sizes)
        system_counts = {k: Counter(v) for k, v in system_sizes.items()}

        recommended_weapons: list[str] = []
        total_dps = 0.0
        total_alpha = 0.0
        any_dps = False
        any_alpha = False

        for size, count in sorted(weapon_counts.items()):
            item = await self._recommend_weapon(size, role_key)
            if item:
                recommended_weapons.append(self._item_line(item, count=count))
                dps, alpha = self._extract_dps_alpha(item)
                if dps is not None:
                    total_dps += dps * count
                    any_dps = True
                if alpha is not None:
                    total_alpha += alpha * count
                    any_alpha = True

        missile_lines = self._extract_missile_lines(vehicle)
        if missile_lines:
            recommended_weapons.extend(missile_lines)

        recommended_systems: list[str] = []
        for category in ("shields", "power", "coolers"):
            for size, count in sorted(system_counts.get(category, Counter()).items()):
                item = await self._recommend_system(category, size, role_key)
                if item:
                    recommended_systems.append(self._item_line(item, count=count))

        if not recommended_weapons:
            recommended_weapons = ["No named weapon recommendation could be derived from the live API for this hull."]
        if not recommended_systems:
            recommended_systems = ["No named system recommendation could be derived from the live API for this hull."]

        perf_lines: list[str] = []
        if any_dps:
            perf_lines.append(f"Estimated pilot / mounted weapon DPS: {_fmt_num(total_dps, 0)}")
        if any_alpha:
            perf_lines.append(f"Estimated alpha strike per volley: {_fmt_num(total_alpha, 0)}")
        if performance.get("hull_hp") is not None:
            perf_lines.append(f"Hull HP: {_fmt_num(performance['hull_hp'], 0)}")
        if performance.get("shield_hp") is not None:
            perf_lines.append(f"Shield HP: {_fmt_num(performance['shield_hp'], 0)}")
        if performance.get("scm_speed") is not None or performance.get("max_speed") is not None:
            perf_lines.append(f"Speed: SCM {_fmt_num(performance.get('scm_speed'), 0)} m/s • Max {_fmt_num(performance.get('max_speed'), 0)} m/s")
        if performance.get("cargo_scu") is not None:
            perf_lines.append(f"Cargo: {_fmt_num(performance['cargo_scu'], 0)} SCU")
        if performance.get("max_crew") is not None:
            perf_lines.append(f"Crew: {performance['max_crew']}")
        if not perf_lines:
            perf_lines.append("Performance stats were not exposed cleanly by the Wiki API for this hull.")

        notes: list[str] = [f"Recommended role profile: {ROLE_DISPLAY.get(role_key, role_key.title())}"]
        notes.extend(hardpoints)
        notes.append("When live Wiki search does not return a clean, valid component, the recommender now falls back to curated named weapons/modules so the build output remains complete.")

        vehicle_name = _first_non_empty(vehicle.get("name"), vehicle.get("game_name"), vehicle.get("name_full"), vehicle.get("title"), ship_name)
        if not isinstance(vehicle_name, str):
            vehicle_name = ship_name

        return LoadoutReport(
            ship_name=vehicle_name,
            role=ROLE_DISPLAY.get(role_key, role_key.title()),
            manufacturer=manufacturer,
            weapons=recommended_weapons,
            systems=recommended_systems,
            performance=perf_lines,
            notes=notes,
        )
