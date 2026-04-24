from __future__ import annotations

import logging
import re
from collections import Counter
from typing import Any
from urllib.parse import quote

import httpx

from .config import settings
from .loadout_engine import LoadoutEngine, ROLE_DISPLAY, ROLE_SYSTEM_PROFILE, SelectedItem
from .models import LoadoutReport

log = logging.getLogger(__name__)


def _norm(text: str | None) -> str:
    return " ".join((text or "").strip().lower().split())


def _fmt_num(value: float | int | None, digits: int = 0) -> str:
    if value is None:
        return "n/a"
    return f"{value:,.{digits}f}"


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _first(*values: Any) -> Any | None:
    for value in values:
        if value is None:
            continue
        if isinstance(value, str):
            if value.strip():
                return value.strip()
        elif isinstance(value, (int, float)):
            return value
        elif value:
            return value
    return None


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.replace(",", "").strip())
        except ValueError:
            return None
    return None


def _to_int(value: Any) -> int | None:
    num = _to_float(value)
    return int(num) if num is not None else None


def _walk_dicts(value: Any):
    if isinstance(value, dict):
        yield value
        for nested in value.values():
            yield from _walk_dicts(nested)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_dicts(item)


def _text_blob(obj: dict[str, Any]) -> str:
    vals = []
    for key in (
        "name", "type", "sub_type", "class", "class_name", "classification", "category",
        "item_type", "port_type", "port_name", "component_type", "component_class", "subtype",
        "itemType", "item_type_label", "title", "subtitle", "display_name",
    ):
        val = obj.get(key)
        if val:
            vals.append(str(val))
    item = obj.get("item") or obj.get("equipped") or obj.get("component")
    if isinstance(item, dict):
        vals.append(_text_blob(item))
    return " ".join(vals).lower()


def _size_from(obj: dict[str, Any]) -> int | None:
    for key in ("size", "port_size", "component_size", "item_size", "vehicle_weapon_size", "sizes"):
        size = _to_int(obj.get(key))
        if size is not None:
            return size
    item = obj.get("item") or obj.get("equipped") or obj.get("component")
    if isinstance(item, dict):
        nested = _size_from(item)
        if nested is not None:
            return nested
    blob = _text_blob(obj)
    size_map = {"vehicle": 0, "small": 1, "medium": 2, "large": 3, "capital": 4}
    for label, numeric in size_map.items():
        if label in blob:
            return numeric
    match = re.search(r"(?:size\s*|\bs)([0-9])\b", blob)
    if match:
        return int(match.group(1))
    return None


def _count_from(obj: dict[str, Any]) -> int:
    for key in ("count", "quantity", "qty", "amount", "mounts"):
        val = _to_int(obj.get(key))
        if val and val > 0:
            return min(val, 16)
    return 1


class WikiClient:
    """Live Wiki data is authoritative for ship slot sizes/counts."""

    def __init__(self, timeout: float = 20.0) -> None:
        self._http = httpx.AsyncClient(
            base_url=settings.wiki_api_base.rstrip("/"),
            timeout=timeout,
            follow_redirects=True,
            headers={"Accept": "application/json", "User-Agent": "CitizenAI-DiscordBot/1.0"},
        )
        self.engine = LoadoutEngine()

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

    async def _json(self, path: str, params: dict[str, Any] | None = None) -> Any | None:
        try:
            response = await self._http.get(path, params=params)
            response.raise_for_status()
            payload = response.json()
            if isinstance(payload, dict) and "data" in payload:
                return payload["data"]
            return payload
        except Exception as exc:
            log.debug("Wiki request failed: %s params=%s error=%s", path, params, exc)
            return None

    async def _vehicle_search(self, query: str) -> list[dict[str, Any]]:
        for path in ("/api/vehicles", "/api/v3/vehicles"):
            data = await self._json(path, {"search": query, "limit": 10})
            if isinstance(data, list):
                return [x for x in data if isinstance(x, dict)]
            if isinstance(data, dict):
                rows = data.get("items") or data.get("results") or data.get("data")
                if isinstance(rows, list):
                    return [x for x in rows if isinstance(x, dict)]
        return []

    def _candidate_score(self, query: str, candidate: dict[str, Any]) -> int:
        q = _norm(query)
        names = []
        for key in ("name", "name_full", "title", "slug", "class_name", "game_name"):
            val = candidate.get(key)
            if isinstance(val, str) and val.strip():
                names.append(_norm(val))
        best = 0
        for name in names:
            if q == name:
                best = max(best, 100)
            elif q in name or name in q:
                best = max(best, 75)
            elif all(part in name for part in q.split()):
                best = max(best, 60)
        return best

    async def _fetch_vehicle(self, ship_name: str) -> dict[str, Any] | None:
        candidates = [ship_name, ship_name.title(), _norm(ship_name).replace(" ", "-")]
        for ident in candidates:
            for path in (f"/api/vehicles/{quote(ident)}", f"/api/v3/vehicles/{quote(ident)}"):
                data = await self._json(path)
                if isinstance(data, dict) and data:
                    return data
        matches = await self._vehicle_search(ship_name)
        if not matches:
            return None
        matches.sort(key=lambda c: self._candidate_score(ship_name, c), reverse=True)
        best = matches[0]
        if self._candidate_score(ship_name, best) < 55:
            return None
        ident = _first(best.get("uuid"), best.get("slug"), best.get("name"), best.get("title"))
        if not isinstance(ident, str):
            return best
        for path in (f"/api/vehicles/{quote(ident)}", f"/api/v3/vehicles/{quote(ident)}"):
            data = await self._json(path)
            if isinstance(data, dict) and data:
                return data
        return best

    def _manufacturer(self, vehicle: dict[str, Any]) -> str:
        val = vehicle.get("manufacturer") or vehicle.get("company") or vehicle.get("manufacturer_data")
        if isinstance(val, dict):
            return str(_first(val.get("name"), val.get("short_name"), val.get("code")) or "Unknown Manufacturer")
        if isinstance(val, str):
            return val
        return "Unknown Manufacturer"

    def _role_from_vehicle(self, vehicle: dict[str, Any], requested_role: str | None) -> str:
        wanted = _norm(requested_role).replace(" ", "_") if requested_role else ""
        if wanted in ROLE_DISPLAY:
            return wanted
        blob = " ".join(str(x) for x in (vehicle.get("role"), vehicle.get("career"), vehicle.get("type"), vehicle.get("focus"), vehicle.get("description")) if x).lower()
        if "heavy" in blob and "fighter" in blob:
            return "heavy_fighter"
        if "interceptor" in blob or "racing" in blob:
            return "interceptor"
        if "stealth" in blob:
            return "stealth"
        if "exploration" in blob or "explorer" in blob:
            return "exploration"
        if "cargo" in blob or "hauling" in blob or "freight" in blob:
            return "cargo"
        if "fighter" in blob or "combat" in blob or "gunship" in blob:
            return "combat"
        return "multirole"

    def _stats_from_vehicle(self, vehicle: dict[str, Any]) -> dict[str, Any]:
        speed = vehicle.get("speed") if isinstance(vehicle.get("speed"), dict) else {}
        shield = vehicle.get("shield") if isinstance(vehicle.get("shield"), dict) else {}
        crew = vehicle.get("crew") if isinstance(vehicle.get("crew"), dict) else vehicle.get("crew")
        return {
            "hull_hp": _to_float(_first(vehicle.get("health"), vehicle.get("hull_hp"), vehicle.get("hit_points"), vehicle.get("hp"))),
            "shield_hp": _to_float(_first(vehicle.get("shield_hp"), vehicle.get("shields_hp"), vehicle.get("shield_health"), shield.get("hp"), shield.get("health"))),
            "scm_speed": _to_float(_first(speed.get("scm"), vehicle.get("scm_speed"))),
            "max_speed": _to_float(_first(speed.get("max"), vehicle.get("max_speed"))),
            "cargo_scu": _to_float(_first(vehicle.get("cargo_capacity"), vehicle.get("cargo_scu"), vehicle.get("cargo"))),
            "crew": _to_int(_first(crew.get("max") if isinstance(crew, dict) else crew, vehicle.get("crew_max"))),
        }

    def _classify_port(self, obj: dict[str, Any]) -> str | None:
        blob = _text_blob(obj)
        port_type = _norm(str(obj.get("type") or obj.get("port_type") or obj.get("item_type") or obj.get("itemType") or ""))
        if any(x in blob for x in ("missile", "torpedo", "rack")):
            return "missiles"
        if "quantum" in blob and "drive" in blob:
            return "quantum_drives"
        if any(x in blob for x in ("shield generator", "shield_generator")) or port_type in {"shield", "shield generator", "shield_generator"}:
            return "shields"
        if any(x in blob for x in ("power plant", "power_plant")) or port_type in {"power", "power plant", "power_plant"}:
            return "power"
        if "cooler" in blob or "cooling" in blob or port_type in {"cooler", "coolers"}:
            return "coolers"
        if any(x in blob for x in ("weapon", "gun", "cannon", "repeater", "gatling", "hardpoint")) and not any(x in blob for x in ("missile", "rack")):
            return "weapons"
        return None

    def _infer_hardpoints(self, vehicle: dict[str, Any]) -> dict[str, list[dict[str, int]]]:
        buckets: dict[str, Counter[int]] = {k: Counter() for k in ("weapons", "missiles", "shields", "power", "coolers", "quantum_drives")}
        seen: set[tuple[str, int, str]] = set()

        roots: list[Any] = []
        for key in ("ports", "components", "parts", "hardpoints", "loadout"):
            roots.extend(_as_list(vehicle.get(key)))
        source = roots if roots else [vehicle]
        candidates = [x for x in _walk_dicts(source) if isinstance(x, dict)][:900]

        for obj in candidates:
            category = self._classify_port(obj)
            if not category:
                continue
            size = _size_from(obj)
            if size is None or size > 7:
                continue
            name = str(_first(obj.get("name"), obj.get("class_name"), obj.get("type"), obj.get("port_type"), obj.get("port_name"), obj.get("title")) or "")[:120]
            key = (category, size, name.lower())
            if key in seen:
                continue
            seen.add(key)
            buckets[category][size] += _count_from(obj)

        caps = {"weapons": 20, "missiles": 64, "shields": 8, "power": 6, "coolers": 8, "quantum_drives": 2}
        out: dict[str, list[dict[str, int]]] = {}
        for category, counts in buckets.items():
            total = 0
            out[category] = []
            for size, count in sorted(counts.items()):
                remaining = caps[category] - total
                if remaining <= 0:
                    break
                safe_count = max(1, min(count, remaining))
                out[category].append({"size": int(size), "count": int(safe_count)})
                total += safe_count
        log.info("Live Wiki slot parse: %s", {k: v for k, v in out.items() if v})
        return out

    def _profile_for_category(self, role: str, category: str) -> str:
        profile = ROLE_SYSTEM_PROFILE.get(role, ROLE_SYSTEM_PROFILE["multirole"])
        if category == "shields":
            return profile["shield"]
        if category == "power":
            return profile["power"]
        if category == "coolers":
            return profile["cooler"]
        if category == "quantum_drives":
            return profile.get("quantum", "balanced")
        return "balanced"

    def _select_system(self, category: str, size: int, count: int, role: str) -> SelectedItem | None:
        by_size = (self.engine.component_db.get("systems", {}).get(category, {}) or {}).get(str(size))
        if not by_size:
            return None
        if "name" in by_size:
            item = by_size
        else:
            profile = self._profile_for_category(role, category)
            item = by_size.get(profile) or by_size.get("balanced") or by_size.get("military") or by_size.get("durable") or next(iter(by_size.values()), None)
        if not item:
            return None
        return SelectedItem(item["name"], int(item["size"]), item["class"], item.get("grade"), count, item.get("component_class"))

    def _dynamic_report(self, vehicle: dict[str, Any], query: str, requested_role: str | None) -> LoadoutReport:
        role = self._role_from_vehicle(vehicle, requested_role)
        hp = self._infer_hardpoints(vehicle)
        stats = self._stats_from_vehicle(vehicle)
        name = str(_first(vehicle.get("name"), vehicle.get("game_name"), vehicle.get("title"), query) or query)
        manufacturer = self._manufacturer(vehicle)

        weapons: list[SelectedItem] = []
        total_dps = 0.0
        total_alpha = 0.0
        for slot in hp.get("weapons", []):
            item = self.engine.select_weapon(int(slot["size"]), role)
            if item:
                item.count = int(slot["count"])
                weapons.append(item)
                total_dps += (item.dps or 0) * item.count
                total_alpha += (item.alpha or 0) * item.count
        for slot in hp.get("missiles", []):
            item = self.engine.select_missile(int(slot["size"]), int(slot["count"]))
            if item:
                weapons.append(item)

        systems: list[SelectedItem] = []
        for category in ("shields", "power", "coolers", "quantum_drives"):
            for slot in hp.get(category, []):
                item = self._select_system(category, int(slot["size"]), int(slot["count"]), role)
                if item:
                    systems.append(item)

        weapon_lines = [x.line() for x in weapons] or ["Live Wiki data did not expose usable weapon hardpoints for this hull."]
        system_lines = [x.line() for x in systems] or ["Live Wiki data did not expose usable system slots for this hull."]

        perf = []
        if total_dps:
            perf.append(f"Recommended weapon DPS: {_fmt_num(total_dps, 0)}")
        if total_alpha:
            perf.append(f"Recommended alpha strike: {_fmt_num(total_alpha, 0)}")
        if stats.get("hull_hp") is not None:
            perf.append(f"Hull HP: {_fmt_num(stats['hull_hp'], 0)}")
        if stats.get("shield_hp") is not None:
            perf.append(f"Shield HP: {_fmt_num(stats['shield_hp'], 0)}")
        if stats.get("scm_speed") is not None or stats.get("max_speed") is not None:
            perf.append(f"Speed: SCM {_fmt_num(stats.get('scm_speed'), 0)} m/s • Max {_fmt_num(stats.get('max_speed'), 0)} m/s")
        if stats.get("cargo_scu") is not None:
            perf.append(f"Cargo: {_fmt_num(stats['cargo_scu'], 0)} SCU")
        if stats.get("crew") is not None:
            perf.append(f"Crew: {stats['crew']}")
        if not perf:
            perf.append("No performance stats were exposed cleanly by the Wiki API.")

        notes = [
            f"Recommended role profile: {ROLE_DISPLAY.get(role, role.title())}",
            "Source: live Star Citizen Wiki ship data is authoritative for slot sizes/counts. Local ship data is not used as fallback.",
        ]
        for key, label in (("weapons", "Weapons"), ("missiles", "Missiles"), ("shields", "Shields"), ("power", "Power"), ("coolers", "Coolers"), ("quantum_drives", "Quantum")):
            slots = hp.get(key, [])
            if slots:
                notes.append(f"{label}: " + " • ".join(f"{s['count']}x S{s['size']}" for s in slots))
        notes.append("Loadout live-data parser: recursively scans Wiki ports/components and only recommends parts after slot size/category parsing succeeds.")

        return LoadoutReport(name, ROLE_DISPLAY.get(role, role.title()), manufacturer, weapon_lines, system_lines, perf, notes)

    async def build_loadout_report(self, ship_name: str, requested_role: str | None = None) -> LoadoutReport | None:
        vehicle = await self._fetch_vehicle(ship_name)
        if not vehicle:
            return None
        return self._dynamic_report(vehicle, ship_name, requested_role)

    async def get_ship(self, ship_name: str) -> dict[str, Any] | None:
        return await self._fetch_vehicle(ship_name)
