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
    "weapon",
    "gun",
    "cannon",
    "repeater",
    "gatling",
    "scattergun",
    "shotgun",
    "laser",
    "ballistic",
    "distortion",
    "plasma",
    "railgun",
    "singe",
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
    "fighter": "Fighter",
    "interceptor": "Interceptor",
    "bomber": "Bomber",
    "racing": "Racing",
    "racer": "Racing",
    "exploration": "Exploration",
    "cargo": "Cargo / Hauling",
    "hauling": "Cargo / Hauling",
    "transport": "Transport",
    "starter": "Starter / Multirole",
    "multirole": "Multirole",
    "industrial": "Industrial",
    "mining": "Mining",
    "salvage": "Salvage",
    "medical": "Medical",
    "dropship": "Dropship",
    "gunship": "Gunship",
    "ground": "Ground Vehicle",
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
    return " ".join(
        part.capitalize() if part.islower() or part.isupper() else part
        for part in text.split()
    )


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

    bad_exact = {
        "weapon",
        "weapons",
        "missile",
        "missiles",
        "shield generator",
        "shield generators",
        "power plant",
        "power plants",
        "cooler",
        "coolers",
        "tbd",
        "unknown",
    }

    normalized = cleaned.lower().replace(" ", "")
    if cleaned.lower() in bad_exact:
        return None
    if normalized.startswith(("rsiweapon", "rsimodular", "vehicleitem")):
        return None
    return cleaned


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


class WikiClient:
    def __init__(self, timeout: float = 20.0) -> None:
        self._http = httpx.AsyncClient(
            base_url=settings.wiki_api_base.rstrip("/"),
            timeout=timeout,
            follow_redirects=True,
            headers={
                "Accept": "application/json",
                "User-Agent": "CitizenAI-DiscordBot/1.0",
            },
        )
        self._vehicle_cache: dict[str, tuple[float, dict[str, Any]]] = {}
        self._search_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}

    async def close(self) -> None:
        await self._http.aclose()

    async def ping(self) -> bool:
        for path in ("/api/vehicles/Gladius", "/api/v3/vehicles/Gladius", "/"):
            try:
                response = await self._http.get(path)
                response.raise_for_status()
                return True
            except Exception as exc:
                log.debug("Wiki ping failed on %s: %s", path, exc)
        return False

    async def _request_json(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        method: str = "GET",
    ) -> Any:
        response = await self._http.request(method, path, params=params, json=json)
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, dict) and "data" in payload:
            return payload["data"]
        return payload

    async def _try_paths(
        self,
        paths: list[tuple[str, str, dict[str, Any] | None, dict[str, Any] | None]],
    ) -> Any | None:
        for method, path, params, json in paths:
            try:
                data = await self._request_json(path, params=params, json=json, method=method)
                if data is not None:
                    return data
            except Exception as exc:
                log.debug("Wiki request failed: %s %s (%s)", method, path, exc)
        return None

    def _vehicle_detail_paths(
        self,
        identifier: str,
    ) -> list[tuple[str, str, dict[str, Any] | None, dict[str, Any] | None]]:
        include = {"include": "components,ports,shops"}
        return [
            ("GET", f"/api/vehicles/{identifier}", include, None),
            ("GET", f"/api/v3/vehicles/{identifier}", include, None),
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
                    results = [
                        x
                        for x in _as_list(data.get("data") or data.get("items") or data.get("results"))
                        if isinstance(x, dict)
                    ]
                if results:
                    break
            except Exception as exc:
                log.debug("Vehicle search attempt failed: %s %s (%s)", method, path, exc)

        self._search_cache[key] = (now, results)
        return results

    def _vehicle_candidate_names(self, candidate: dict[str, Any]) -> list[str]:
        names: list[str] = []
        for key in ("name", "name_full", "slug", "uuid", "title", "class_name"):
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
            norm_names = {_norm(name) for name in names}

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

        out: list[str] = []
        for value in candidates:
            if value and value not in out:
                out.append(value)
            encoded = quote(value) if value else ""
            if encoded and encoded not in out:
                out.append(encoded)

        return out

    async def _fetch_vehicle(self, ship_name: str) -> dict[str, Any] | None:
        normalized = _norm(ship_name)

        hard_uuid = HARD_UUID_LOOKUPS.get(normalized)
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
            vehicle.get("type"),
            vehicle.get("focus"),
            vehicle.get("career"),
            vehicle.get("role"),
            vehicle.get("vehicle_role"),
            vehicle.get("vehicle_roles"),
            vehicle.get("description"),
        ]

        text_chunks: list[str] = []
        for candidate in candidates:
            if isinstance(candidate, list):
                text_chunks.extend(str(item) for item in candidate if item)
            elif candidate:
                text_chunks.append(str(candidate))

        for chunk in text_chunks:
            lowered = chunk.lower()
            for key, label in ROLE_HINTS.items():
                if key in lowered:
                    return label

        return _titleize(str(text_chunks[0])) or "Unknown Role" if text_chunks else "Unknown Role"

    def _extract_manufacturer(self, vehicle: dict[str, Any]) -> str:
        return (
            _manufacturer_name(
                _first_non_empty(
                    vehicle.get("manufacturer"),
                    vehicle.get("manufacturer_data"),
                    vehicle.get("company"),
                )
            )
            or "Unknown Manufacturer"
        )

    def _extract_performance(self, vehicle: dict[str, Any]) -> dict[str, Any]:
        speed = vehicle.get("speed") or {}
        crew = vehicle.get("crew") or {}

        hull_hp = _to_float(
            _first_non_empty(
                vehicle.get("health"),
                vehicle.get("hull_hp"),
                vehicle.get("hit_points"),
                vehicle.get("hp"),
            )
        )

        shield_hp = _to_float(
            _first_non_empty(
                vehicle.get("shield_hp"),
                vehicle.get("shields_hp"),
                vehicle.get("shield_health"),
                (vehicle.get("shield") or {}).get("health")
                if isinstance(vehicle.get("shield"), dict)
                else None,
            )
        )

        return {
            "scm_speed": _to_float(speed.get("scm") if isinstance(speed, dict) else None),
            "max_speed": _to_float(speed.get("max") if isinstance(speed, dict) else None),
            "hull_hp": hull_hp,
            "shield_hp": shield_hp,
            "cargo_scu": _to_float(
                _first_non_empty(
                    vehicle.get("cargo_capacity"),
                    vehicle.get("cargo"),
                    vehicle.get("cargo_scu"),
                )
            ),
            "max_crew": _first_non_empty(
                crew.get("max") if isinstance(crew, dict) else crew,
                vehicle.get("crew_max"),
            ),
        }

    def _extract_port_records(self, vehicle: dict[str, Any]) -> list[dict[str, Any]]:
        return [item for item in _iter_dicts(vehicle.get("ports") or []) if isinstance(item, dict)]

    def _extract_components_root(self, vehicle: dict[str, Any]) -> list[dict[str, Any]]:
        return [item for item in _as_list(vehicle.get("components") or []) if isinstance(item, dict)]

    def _candidate_text(self, obj: dict[str, Any]) -> str:
        fields = [
            obj.get("type"),
            obj.get("sub_type"),
            obj.get("group"),
            obj.get("name"),
            obj.get("class_name"),
            obj.get("port_type"),
            obj.get("item_type"),
            obj.get("category"),
        ]
        text = " ".join(str(value) for value in fields if value)
        for nested_key in ("item", "component", "specs", "details", "weapon_data", "mounted_item", "equipped_item"):
            nested = obj.get(nested_key)
            if isinstance(nested, dict):
                text += " " + self._candidate_text(nested)
        return text.strip()

    def _extract_size(self, obj: dict[str, Any]) -> str | None:
        candidates = [
            obj.get("component_size"),
            obj.get("size"),
            obj.get("port_size"),
            obj.get("item_size"),
            obj.get("vehicle_weapon_size"),
            (obj.get("specs") or {}).get("size") if isinstance(obj.get("specs"), dict) else None,
            (obj.get("details") or {}).get("size") if isinstance(obj.get("details"), dict) else None,
            (obj.get("item") or {}).get("size") if isinstance(obj.get("item"), dict) else None,
            (obj.get("component") or {}).get("size") if isinstance(obj.get("component"), dict) else None,
        ]
        value = _first_non_empty(*candidates)
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return str(int(value))
        return str(value)

    def _extract_item_name(self, obj: dict[str, Any]) -> str | None:
        nested_candidates = []
        for nested_key in ("item", "component", "mounted_item", "equipped_item", "details", "specs", "weapon_data"):
            nested = obj.get(nested_key)
            if isinstance(nested, dict):
                nested_candidates.append(
                    _first_non_empty(
                        nested.get("name"),
                        nested.get("name_full"),
                        nested.get("label"),
                        nested.get("title"),
                    )
                )

        value = _first_non_empty(
            obj.get("name"),
            obj.get("name_full"),
            obj.get("label"),
            obj.get("title"),
            *nested_candidates,
        )
        if not isinstance(value, str):
            return None
        return _clean_placeholder_name(value)

    def _extract_item_class_and_grade(self, obj: dict[str, Any]) -> tuple[str | None, str | None]:
        family_candidates = [
            obj.get("item_class"),
            obj.get("class"),
            obj.get("type_class"),
            obj.get("sub_type"),
            (obj.get("specs") or {}).get("class") if isinstance(obj.get("specs"), dict) else None,
            (obj.get("details") or {}).get("class") if isinstance(obj.get("details"), dict) else None,
        ]
        grade_candidates = [
            obj.get("component_class"),
            obj.get("grade"),
            (obj.get("specs") or {}).get("grade") if isinstance(obj.get("specs"), dict) else None,
            (obj.get("details") or {}).get("grade") if isinstance(obj.get("details"), dict) else None,
        ]

        family_raw = _first_non_empty(*family_candidates)
        grade_raw = _first_non_empty(*grade_candidates)

        family = None
        if family_raw is not None:
            family_text = str(family_raw).strip()
            if family_text and not family_text.upper().startswith("RSI"):
                family = _titleize(family_text)

        grade = None
        if grade_raw is not None:
            grade_text = str(grade_raw).strip().upper()
            if grade_text and not grade_text.startswith("RSI") and grade_text != "TBD":
                grade = grade_text

        return family, grade

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
                obj.get("weapon_data"),
                obj.get("specs"),
                obj.get("details"),
                obj.get("item"),
                obj.get("component"),
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

        rpm = _to_float(
            _first_non_empty(
                obj.get("rpm"),
                obj.get("fire_rate"),
                obj.get("rate_of_fire"),
                (obj.get("weapon_data") or {}).get("rpm")
                if isinstance(obj.get("weapon_data"), dict)
                else None,
            )
        )

        if damage_total is not None:
            dps = damage_total * (rpm / 60.0) if rpm else None
            return dps, damage_total

        return None, None

    def _extract_count(self, obj: dict[str, Any]) -> int:
        for key in ("count", "quantity", "qty", "amount"):
            raw = obj.get(key)
            try:
                if raw is not None and int(float(raw)) > 0:
                    return int(float(raw))
            except Exception:
                pass
        return 1

    def _component_line(self, obj: dict[str, Any]) -> tuple[str | None, str | None]:
        category = _classify_from_text(self._candidate_text(obj))
        if not category:
            return None, None

        name = self._extract_item_name(obj) or category.title()
        size = self._extract_size(obj)
        item_class, grade = self._extract_item_class_and_grade(obj)
        dps, alpha = self._extract_dps_alpha(obj)
        count = self._extract_count(obj)

        attrs = []
        if size:
            attrs.append(f"Size {size}")
        if item_class:
            attrs.append(f"Class {item_class}")
        if grade:
            attrs.append(f"Grade {grade}")
        if category == "weapons" and dps is not None:
            attrs.append(f"{_fmt_num(dps, 0)} DPS each")
        if category == "weapons" and alpha is not None:
            attrs.append(f"{_fmt_num(alpha, 0)} alpha")

        prefix = f"{count}x " if count > 1 else ""
        line = f"{prefix}{name}" + (f" — {' • '.join(attrs)}" if attrs else "")
        return category, line

    def _extract_component_lines(self, vehicle: dict[str, Any]) -> dict[str, list[str]]:
        grouped: dict[str, list[str]] = defaultdict(list)

        for obj in self._extract_components_root(vehicle):
            category, line = self._component_line(obj)
            if category and line:
                grouped[category].append(line)

        if not grouped:
            for port in self._extract_port_records(vehicle):
                for nested_key in ("item", "component", "mounted_item", "equipped_item", "details", "specs", "weapon_data"):
                    nested = port.get(nested_key)
                    if isinstance(nested, dict):
                        category, line = self._component_line(nested)
                        if category and line:
                            grouped[category].append(line)
                            break

        return grouped

    def _extract_hardpoint_summary(self, vehicle: dict[str, Any]) -> list[str]:
        counts: dict[str, Counter[str]] = {
            key: Counter() for key in ("weapons", "missiles", "shields", "power", "coolers")
        }

        for port in self._extract_port_records(vehicle):
            category = _classify_from_text(self._candidate_text(port))
            if category not in counts:
                continue
            size = self._extract_size(port) or "?"
            counts[category][size] += 1

        lines: list[str] = []
        labels = {
            "weapons": "Weapons",
            "missiles": "Missiles",
            "shields": "Shield Generators",
            "power": "Power Plants",
            "coolers": "Coolers",
        }

        for category in ("weapons", "missiles", "shields", "power", "coolers"):
            bucket = counts[category]
            if not bucket:
                continue
            parts = [
                f"{count}x S{size}" if size != "?" else f"{count}x size unknown"
                for size, count in sorted(bucket.items())
            ]
            lines.append(f"{labels[category]}: {' • '.join(parts)}")

        return lines

    def _weapon_totals(self, vehicle: dict[str, Any]) -> tuple[float | None, float | None]:
        total_dps = 0.0
        total_alpha = 0.0
        any_dps = False
        any_alpha = False

        for obj in self._extract_components_root(vehicle):
            category = _classify_from_text(self._candidate_text(obj))
            if category != "weapons":
                continue

            count = self._extract_count(obj)
            dps, alpha = self._extract_dps_alpha(obj)
            if dps is not None:
                total_dps += dps * max(1, count)
                any_dps = True
            if alpha is not None:
                total_alpha += alpha * max(1, count)
                any_alpha = True

        return (total_dps if any_dps else None, total_alpha if any_alpha else None)

    async def build_loadout_report(self, ship_name: str) -> LoadoutReport | None:
        vehicle = await self.get_ship(ship_name)
        if vehicle is None:
            return None

        vehicle_name = _first_non_empty(
            vehicle.get("name"),
            vehicle.get("name_full"),
            vehicle.get("title"),
            ship_name,
        )
        if not isinstance(vehicle_name, str):
            vehicle_name = ship_name

        role = self._extract_role(vehicle)
        manufacturer = self._extract_manufacturer(vehicle)
        performance = self._extract_performance(vehicle)
        grouped = self._extract_component_lines(vehicle)
        hardpoints = self._extract_hardpoint_summary(vehicle)

        weapon_lines = grouped.get("weapons", []) + grouped.get("missiles", [])
        if not weapon_lines:
            weapon_lines = ["No named compatible weapons were exposed by the Wiki API for this hull."]

        system_lines = grouped.get("shields", []) + grouped.get("power", []) + grouped.get("coolers", [])
        if not system_lines:
            system_lines = ["No named system components were exposed by the Wiki API for this hull."]

        perf_lines: list[str] = []
        total_dps, total_alpha = self._weapon_totals(vehicle)
        if total_dps is not None:
            perf_lines.append(f"Estimated pilot / mounted weapon DPS: {_fmt_num(total_dps, 0)}")
        if total_alpha is not None:
            perf_lines.append(f"Estimated alpha strike per volley: {_fmt_num(total_alpha, 0)}")
        if performance.get("hull_hp") is not None:
            perf_lines.append(f"Hull HP: {_fmt_num(performance['hull_hp'], 0)}")
        if performance.get("shield_hp") is not None:
            perf_lines.append(f"Shield HP: {_fmt_num(performance['shield_hp'], 0)}")
        if performance.get("scm_speed") is not None or performance.get("max_speed") is not None:
            perf_lines.append(
                f"Speed: SCM {_fmt_num(performance.get('scm_speed'), 0)} m/s • Max {_fmt_num(performance.get('max_speed'), 0)} m/s"
            )
        if performance.get("cargo_scu") is not None:
            perf_lines.append(f"Cargo: {_fmt_num(performance['cargo_scu'], 0)} SCU")
        if performance.get("max_crew") is not None:
            perf_lines.append(f"Crew: {performance['max_crew']}")
        if not perf_lines:
            perf_lines.append("Performance stats were not exposed cleanly by the Wiki API for this hull.")

        notes: list[str] = []
        if hardpoints:
            notes.extend(hardpoints)
        notes.append("This report is based only on data exposed by the Star Citizen Wiki API for this vehicle.")

        return LoadoutReport(
            ship_name=vehicle_name,
            role=role,
            manufacturer=manufacturer,
            weapons=weapon_lines,
            systems=system_lines,
            performance=perf_lines,
            notes=notes,
        )
