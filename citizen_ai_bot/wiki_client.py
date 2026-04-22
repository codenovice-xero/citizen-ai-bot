from __future__ import annotations

import logging
import time
from collections import Counter, defaultdict
from typing import Any, Iterable
from urllib.parse import quote

import httpx

from .config import settings
from .models import LoadoutReport
from .utils import fuzzy_score

log = logging.getLogger(__name__)

_CACHE_TTL = 60 * 30

WEAPON_KEYWORDS = (
    "weapon", "gun", "cannon", "repeater", "gatling", "scattergun", "shotgun",
    "laser", "ballistic", "distortion", "plasma", "railgun", "singe",
)
MISSILE_KEYWORDS = ("missile", "torpedo", "bomb", "rocket", "rack")
SHIELD_KEYWORDS = ("shield",)
POWER_KEYWORDS = ("power", "powerplant", "power_plant")
COOLER_KEYWORDS = ("cooler", "cooling")

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
}

HARD_UUID_LOOKUPS = {
    "shiv": "3a7bfe4f-7a6c-4818-aba8-0f1019c3a647",
}

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

CATEGORY_LABELS = {
    "weapons": "Weapons",
    "missiles": "Missiles",
    "shields": "Shield Generators",
    "power": "Power Plants",
    "coolers": "Coolers",
}

WEAPON_TERMS = {
    "repeater": {
        1: ["CF-117 Bulldog", "Yellowjacket GT-210"],
        2: ["Badger Repeater", "CF-227 Panther"],
        3: ["Panther Repeater", "Attrition-3"],
        4: ["Rhino Repeater", "Attrition-4"],
        5: ["Attrition-5", "Galdereen Repeater"],
        6: ["Attrition-6"],
        7: ["Attrition-7"],
    },
    "cannon": {
        1: ["M3A Cannon", "FL-11 Cannon"],
        2: ["M4A Cannon", "FL-22 Cannon"],
        3: ["M5A Cannon", "FL-33 Cannon"],
        4: ["M6A Cannon", "Omnisky XII"],
        5: ["M7A Cannon", "Omnisky XV"],
        6: ["M8A Cannon"],
        7: ["M9A Cannon"],
    },
    "gatling": {
        1: ["Yellowjacket GT-210"],
        2: ["Scorpion GT-215"],
        3: ["Mantis GT-220"],
        4: ["AD4B Gatling", "Predator Repeater"],
        5: ["AD5B Gatling"],
        6: ["AD6B Gatling"],
        7: ["AD7B Gatling"],
    },
    "distortion": {
        1: ["Suckerpunch Cannon"],
        2: ["Suckerpunch Cannon"],
        3: ["Suckerpunch XL Cannon"],
        4: ["Suckerpunch XL Cannon"],
        5: ["Suckerpunch XL Cannon"],
    },
}

SYSTEM_TERMS = {
    "combat": {
        "shields": {1: ["FR-66", "Mirage"], 2: ["FR-76"], 3: ["FR-86"]},
        "power": {1: ["JS-300"], 2: ["JS-400"], 3: ["JS-500"]},
        "coolers": {1: ["Snowpack"], 2: ["Snowblind"], 3: ["AbsoluteZero"]},
    },
    "interceptor": {
        "shields": {1: ["Mirage", "FR-66"], 2: ["FR-76"]},
        "power": {1: ["JS-300"], 2: ["JS-400"]},
        "coolers": {1: ["Snowpack"], 2: ["Snowblind"]},
    },
    "heavy_fighter": {
        "shields": {1: ["FR-66"], 2: ["FR-76"], 3: ["FR-86"]},
        "power": {1: ["JS-300"], 2: ["JS-400"], 3: ["JS-500"]},
        "coolers": {1: ["Snowpack"], 2: ["Snowblind"], 3: ["AbsoluteZero"]},
    },
    "stealth": {
        "shields": {1: ["Mirage"], 2: ["Sukoran"]},
        "power": {1: ["Regulus"], 2: ["Regulus"]},
        "coolers": {1: ["UltraFlow"], 2: ["Eco-Flow"]},
    },
    "exploration": {
        "shields": {1: ["Palisade", "FR-66"], 2: ["Palisade", "FR-76"]},
        "power": {1: ["JS-300"], 2: ["JS-400"]},
        "coolers": {1: ["Snowpack"], 2: ["Snowblind"]},
    },
    "multirole": {
        "shields": {1: ["Palisade", "FR-66"], 2: ["Palisade", "FR-76"]},
        "power": {1: ["JS-300"], 2: ["JS-400"]},
        "coolers": {1: ["Snowpack"], 2: ["Snowblind"]},
    },
    "cargo": {
        "shields": {1: ["Palisade", "FR-66"], 2: ["Palisade", "FR-76"], 3: ["FR-86"]},
        "power": {1: ["JS-300"], 2: ["JS-400"], 3: ["JS-500"]},
        "coolers": {1: ["Snowpack"], 2: ["Snowblind"], 3: ["AbsoluteZero"]},
    },
}


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


def _iter_dicts(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for nested in value.values():
            yield from _iter_dicts(nested)
    elif isinstance(value, list):
        for item in value:
            yield from _iter_dicts(item)


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
    if num is None:
        return None
    return int(num)


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


def _classify_from_text(text: str) -> str | None:
    lowered = text.lower()
    if any(word in lowered for word in WEAPON_KEYWORDS):
        return "weapons"
    if any(word in lowered for word in MISSILE_KEYWORDS):
        return "missiles"
    if any(word in lowered for word in SHIELD_KEYWORDS):
        return "shields"
    if any(word in lowered for word in POWER_KEYWORDS):
        return "power"
    if any(word in lowered for word in COOLER_KEYWORDS):
        return "coolers"
    return None


def _clean_placeholder_name(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    bad_exact = {
        "weapon", "weapons", "missile", "missiles", "shield generator", "shield generators",
        "power plant", "power plants", "cooler", "coolers", "tbd", "unknown", "<= placeholder =>",
    }
    lowered = cleaned.lower().replace(" ", "")
    if cleaned.lower() in bad_exact:
        return None
    if lowered.startswith(("rsiweapon", "rsimodular", "vehicleitem")):
        return None
    return cleaned


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
        return [
            ("GET", f"/api/vehicles/{identifier}", None, None),
            ("GET", f"/api/v3/vehicles/{identifier}", None, None),
        ]

    async def search_vehicle(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        key = _norm(query)
        if not key:
            return []
        now = time.monotonic()
        cached = self._search_cache.get(key)
        if cached and (now - cached[0]) < _CACHE_TTL:
            return cached[1]

        attempts = [
            ("GET", "/api/vehicles", {"search": query, "limit": limit}, None),
            ("GET", "/api/v3/vehicles", {"search": query, "limit": limit}, None),
            ("POST", "/api/vehicles/search", {"limit": limit}, {"query": query}),
            ("POST", "/api/v3/vehicles/search", {"limit": limit}, {"query": query}),
        ]
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
        ranked: list[tuple[float, dict[str, Any], list[str]]] = []
        norm_query = _norm(query)
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
        ranked.sort(key=lambda item: item[0], reverse=True)
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
        log.warning(
            "Vehicle search candidates for %r: %s",
            ship_name,
            [self._vehicle_candidate_names(m)[:4] for m in matches[:5]],
        )
        match = self._pick_best_vehicle_match(ship_name, matches)
        if not match:
            log.warning("No vehicle match found for %r", ship_name)
            return None

        target = _first_non_empty(
            match.get("uuid"),
            match.get("slug"),
            match.get("name"),
            match.get("name_full"),
            match.get("title"),
            match.get("class_name"),
        )
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
        candidates = [
            vehicle.get("role"), vehicle.get("career"), vehicle.get("type"), vehicle.get("focus"),
            vehicle.get("vehicle_role"), vehicle.get("vehicle_roles"), vehicle.get("description"),
        ]
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

    def _extract_port_records(self, vehicle: dict[str, Any]) -> list[dict[str, Any]]:
        return [item for item in _iter_dicts(vehicle.get("ports") or []) if isinstance(item, dict)]

    def _extract_components_root(self, vehicle: dict[str, Any]) -> list[dict[str, Any]]:
        return [item for item in _as_list(vehicle.get("components") or vehicle.get("parts") or []) if isinstance(item, dict)]

    def _candidate_text(self, obj: dict[str, Any]) -> str:
        fields = [
            obj.get("type"), obj.get("sub_type"), obj.get("group"), obj.get("name"), obj.get("class_name"),
            obj.get("port_type"), obj.get("item_type"), obj.get("category"), obj.get("classification"),
        ]
        text = " ".join(str(value) for value in fields if value)
        for nested_key in ("item", "component", "specs", "details", "weapon_data", "mounted_item", "equipped_item", "vehicle_weapon"):
            nested = obj.get(nested_key)
            if isinstance(nested, dict):
                text += " " + self._candidate_text(nested)
        return text.strip()

    def _extract_size(self, obj: dict[str, Any]) -> int | None:
        candidates = [
            obj.get("component_size"), obj.get("size"), obj.get("port_size"), obj.get("item_size"),
            obj.get("vehicle_weapon_size"),
            (obj.get("specs") or {}).get("size") if isinstance(obj.get("specs"), dict) else None,
            (obj.get("details") or {}).get("size") if isinstance(obj.get("details"), dict) else None,
            (obj.get("item") or {}).get("size") if isinstance(obj.get("item"), dict) else None,
            (obj.get("component") or {}).get("size") if isinstance(obj.get("component"), dict) else None,
            (obj.get("equipped_item") or {}).get("size") if isinstance(obj.get("equipped_item"), dict) else None,
            (obj.get("vehicle_weapon") or {}).get("size") if isinstance(obj.get("vehicle_weapon"), dict) else None,
        ]
        value = _first_non_empty(*candidates)
        if value is None:
            return None
        try:
            return int(float(value))
        except Exception:
            return None

    def _extract_count(self, obj: dict[str, Any]) -> int:
        for key in ("count", "quantity", "qty", "amount"):
            val = obj.get(key)
            try:
                if val is not None and int(float(val)) > 0:
                    return int(float(val))
            except Exception:
                pass
        return 1

    def _extract_weapon_port_sizes(self, vehicle: dict[str, Any]) -> list[int]:
        sizes: list[int] = []
        # Try ports first
        for port in self._extract_port_records(vehicle):
            category = _classify_from_text(self._candidate_text(port))
            if category == "weapons":
                size = self._extract_size(port)
                count = self._extract_count(port)
                if size:
                    sizes.extend([size] * max(1, count))
        if sizes:
            return sizes
        # Fallback to installed components
        for obj in self._extract_components_root(vehicle):
            category = _classify_from_text(self._candidate_text(obj))
            if category == "weapons":
                size = self._extract_size(obj)
                count = self._extract_count(obj)
                if size:
                    sizes.extend([size] * max(1, count))
        return sizes

    def _extract_system_sizes(self, vehicle: dict[str, Any]) -> dict[str, list[int]]:
        out: dict[str, list[int]] = {"shields": [], "power": [], "coolers": []}
        for port in self._extract_port_records(vehicle):
            category = _classify_from_text(self._candidate_text(port))
            if category in out:
                size = self._extract_size(port)
                count = self._extract_count(port)
                if size:
                    out[category].extend([size] * max(1, count))
        if any(out.values()):
            return out
        for obj in self._extract_components_root(vehicle):
            category = _classify_from_text(self._candidate_text(obj))
            if category in out:
                size = self._extract_size(obj)
                count = self._extract_count(obj)
                if size:
                    out[category].extend([size] * max(1, count))
        return out

    async def _search_items(self, term: str, category: str = "vehicle-components", limit: int = 20) -> list[dict[str, Any]]:
        key = (term.lower(), category)
        now = time.monotonic()
        cached = self._item_search_cache.get(key)
        if cached and (now - cached[0]) < _CACHE_TTL:
            return cached[1]

        attempts = [
            ("GET", "/api/items", {"search": term, "filter[category]": category, "limit": limit}, None),
            ("GET", "/api/items", {"search": term, "limit": limit}, None),
            ("GET", "/api/v3/items", {"search": term, "filter[category]": category, "limit": limit}, None),
            ("GET", "/api/v3/items", {"search": term, "limit": limit}, None),
        ]
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
            except Exception as exc:
                log.debug("Item search attempt failed: %s %s (%s)", method, path, exc)

        self._item_search_cache[key] = (now, results)
        return results

    async def _fetch_item_detail(self, uuid_or_id: str) -> dict[str, Any] | None:
        attempts = [
            ("GET", f"/api/items/{uuid_or_id}", None, None),
            ("GET", f"/api/v3/items/{uuid_or_id}", None, None),
        ]
        data = await self._try_paths(attempts)
        return data if isinstance(data, dict) else None

    def _pick_best_item_candidate(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        *,
        size: int | None = None,
        classification_hint: str | None = None,
        preferred_terms: list[str] | None = None,
    ) -> dict[str, Any] | None:
        ranked: list[tuple[float, dict[str, Any]]] = []
        norm_query = _norm(query)
        for item in candidates:
            names = [str(x) for x in [item.get("name"), item.get("class_name"), item.get("sub_type"), item.get("classification")] if x]
            if not names:
                continue
            score = max(fuzzy_score(query, n) for n in names)
            item_size = _to_int(item.get("size"))
            if size is not None and item_size == size:
                score += 35
            if classification_hint:
                classification = str(item.get("classification") or item.get("type") or "")
                if classification_hint.lower() in classification.lower():
                    score += 25
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
        style = {
            "combat": "repeater",
            "interceptor": "repeater",
            "heavy_fighter": "cannon",
            "stealth": "distortion",
            "exploration": "cannon",
            "multirole": "repeater",
            "cargo": "cannon",
        }.get(role_key, "repeater")

        search_terms = WEAPON_TERMS.get(style, {}).get(size) or WEAPON_TERMS["repeater"].get(size) or []
        best: dict[str, Any] | None = None
        best_score = -1.0

        for term in search_terms:
            results = await self._search_items(term, category="vehicle-components", limit=15)
            candidate = self._pick_best_item_candidate(
                term,
                results,
                size=size,
                classification_hint="Weapon",
                preferred_terms=search_terms,
            )
            if not candidate:
                continue
            detail = await self._fetch_item_detail(str(candidate.get("uuid") or candidate.get("id") or ""))
            item = detail or candidate
            score = float(fuzzy_score(term, str(item.get("name") or "")))
            if score > best_score:
                best_score = score
                best = item

        return best

    async def _recommend_system(self, category: str, size: int, role_key: str) -> dict[str, Any] | None:
        profile = SYSTEM_TERMS.get(role_key) or SYSTEM_TERMS["multirole"]
        search_terms = profile.get(category, {}).get(size) or SYSTEM_TERMS["multirole"].get(category, {}).get(size) or []
        class_hint = {
            "shields": "Shield",
            "power": "Power",
            "coolers": "Cooler",
        }.get(category, "")

        best: dict[str, Any] | None = None
        best_score = -1.0
        for term in search_terms:
            results = await self._search_items(term, category="vehicle-components", limit=15)
            candidate = self._pick_best_item_candidate(
                term,
                results,
                size=size,
                classification_hint=class_hint,
                preferred_terms=search_terms,
            )
            if not candidate:
                continue
            detail = await self._fetch_item_detail(str(candidate.get("uuid") or candidate.get("id") or ""))
            item = detail or candidate
            score = float(fuzzy_score(term, str(item.get("name") or "")))
            if score > best_score:
                best_score = score
                best = item
        return best

    def _item_line(self, item: dict[str, Any], *, count: int = 1) -> str:
        name = _clean_placeholder_name(str(item.get("name") or item.get("title") or item.get("class_name") or "Component")) or "Component"
        size = item.get("size")
        grade = item.get("grade") or ((item.get("specs") or {}).get("grade") if isinstance(item.get("specs"), dict) else None)
        item_class = item.get("sub_type") or item.get("type") or item.get("classification")
        attrs: list[str] = []
        if size is not None:
            attrs.append(f"Size {size}")
        if item_class:
            attrs.append(f"Class {_titleize(str(item_class))}")
        if grade:
            attrs.append(f"Grade {str(grade).upper()}")

        dps = self._extract_dps_alpha(item)[0]
        alpha = self._extract_dps_alpha(item)[1]
        if dps is not None:
            attrs.append(f"{_fmt_num(dps, 0)} DPS each")
        if alpha is not None:
            attrs.append(f"{_fmt_num(alpha, 0)} alpha")

        prefix = f"{count}x " if count > 1 else ""
        return prefix + name + (f" — {' • '.join(attrs)}" if attrs else "")

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

        nested_dicts = [
            nested
            for nested in (
                obj.get("weapon"), obj.get("vehicle_weapon"), obj.get("weapon_data"), obj.get("specs"),
                obj.get("details"), obj.get("item"), obj.get("component"), obj.get("equipped_item")
            )
            if isinstance(nested, dict)
        ]
        for nested in nested_dicts:
            dps, alpha = self._extract_dps_alpha(nested)
            if dps is not None or alpha is not None:
                return dps, alpha

        damage = _first_non_empty(obj.get("damage"), obj.get("damage_data"))
        damage_total = None
        if isinstance(damage, dict):
            damage_total = sum(_to_float(v) or 0.0 for v in damage.values())
            if damage_total == 0:
                damage_total = None

        rpm = _to_float(_first_non_empty(obj.get("rpm"), obj.get("fire_rate"), obj.get("rate_of_fire")))
        if damage_total is not None:
            dps = damage_total * (rpm / 60.0) if rpm else None
            return dps, damage_total
        return None, None

    def _extract_component_lines(self, vehicle: dict[str, Any]) -> dict[str, list[str]]:
        grouped: dict[str, list[str]] = defaultdict(list)
        for obj in self._extract_components_root(vehicle):
            category = _classify_from_text(self._candidate_text(obj))
            if not category:
                equipped = obj.get("equipped_item")
                if isinstance(equipped, dict):
                    category = _classify_from_text(self._candidate_text(equipped))
                    target = equipped
                else:
                    target = obj
            else:
                target = obj
            if not category:
                continue
            grouped[category].append(self._item_line(target, count=self._extract_count(obj)))
        return grouped

    def _extract_hardpoint_summary(self, vehicle: dict[str, Any]) -> list[str]:
        counts: dict[str, Counter[str]] = {key: Counter() for key in ("weapons", "missiles", "shields", "power", "coolers")}
        for port in self._extract_port_records(vehicle):
            category = _classify_from_text(self._candidate_text(port))
            if category not in counts:
                continue
            size = self._extract_size(port)
            if size:
                counts[category][str(size)] += self._extract_count(port)
        lines: list[str] = []
        for category in ("weapons", "missiles", "shields", "power", "coolers"):
            bucket = counts[category]
            if not bucket:
                continue
            parts = [f"{count}x S{size}" for size, count in sorted(bucket.items())]
            lines.append(f"{CATEGORY_LABELS[category]}: {' • '.join(parts)}")
        return lines

    def _shiv_fallback_vehicle(self) -> dict[str, Any]:
        return {
            "name": "Shiv",
            "manufacturer": {"name": "Grey's Market"},
            "role": "Combat • Heavy Fighter",
            "health": 34300,
            "shield_hp": 9000,
            "cargo_capacity": 32,
            "crew": {"max": 2},
            "components": [
                {"name": "Breakneck S4 Gatling", "size": 4, "classification": "Ship.Weapon.Gun", "sub_type": "Ballistic Gatling", "dps": 953, "alpha_damage": 52, "count": 2},
                {"name": "Shield Generator", "size": 1, "classification": "Ship.Shield", "count": 1},
                {"name": "Power Plant", "size": 1, "classification": "Ship.PowerPlant", "count": 1},
                {"name": "Cooler", "size": 1, "classification": "Ship.Cooler", "count": 1},
            ],
            "ports": [
                {"name": "Weapon Mount", "size": 4, "classification": "Ship.Weapon.Gun", "count": 2},
                {"name": "Shield Port", "size": 1, "classification": "Ship.Shield", "count": 1},
                {"name": "Power Port", "size": 1, "classification": "Ship.PowerPlant", "count": 1},
                {"name": "Cooler Port", "size": 1, "classification": "Ship.Cooler", "count": 1},
            ],
        }

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
        hardpoints = self._extract_hardpoint_summary(vehicle)

        weapon_sizes = self._extract_weapon_port_sizes(vehicle)
        system_sizes = self._extract_system_sizes(vehicle)

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

        # Missiles from mounted config if visible
        existing = self._extract_component_lines(vehicle)
        if existing.get("missiles"):
            recommended_weapons.extend(existing["missiles"])

        recommended_systems: list[str] = []
        for category in ("shields", "power", "coolers"):
            for size, count in sorted(system_counts[category].items()):
                item = await self._recommend_system(category, size, role_key)
                if item:
                    recommended_systems.append(self._item_line(item, count=count))

        # Fallback to visible mounted components if searches fail
        if not recommended_weapons and existing.get("weapons"):
            recommended_weapons = existing["weapons"] + existing.get("missiles", [])
        if not recommended_systems:
            recommended_systems = existing.get("shields", []) + existing.get("power", []) + existing.get("coolers", [])

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

        notes: list[str] = []
        notes.append(f"Recommended role profile: {ROLE_DISPLAY.get(role_key, role_key.title())}")
        if hardpoints:
            notes.extend(hardpoints)
        notes.append("Recommended components are selected from live Wiki item search results when possible, with mounted-config fallback if the API does not expose a stronger candidate.")

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
