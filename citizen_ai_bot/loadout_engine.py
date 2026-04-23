from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .models import LoadoutReport

DATA_DIR = Path(__file__).parent / "data"
SHIP_DB_PATH = DATA_DIR / "ship_loadouts.json"
COMPONENT_DB_PATH = DATA_DIR / "components.json"

ROLE_DISPLAY = {
    "combat": "Combat",
    "interceptor": "Interceptor",
    "heavy_fighter": "Heavy Fighter",
    "stealth": "Stealth",
    "exploration": "Exploration",
    "multirole": "Multirole",
    "cargo": "Cargo",
}

ROLE_WEAPON_STYLE = {
    "combat": "repeater",
    "interceptor": "repeater",
    "heavy_fighter": "cannon",
    "stealth": "distortion",
    "exploration": "cannon",
    "multirole": "repeater",
    "cargo": "cannon",
}

ROLE_SYSTEM_PROFILE = {
    "combat": {"shield": "military", "power": "military", "cooler": "military"},
    "interceptor": {"shield": "fast-recharge", "power": "military", "cooler": "military"},
    "heavy_fighter": {"shield": "military", "power": "military", "cooler": "military"},
    "stealth": {"shield": "stealth", "power": "stealth", "cooler": "stealth"},
    "exploration": {"shield": "durable", "power": "reliable", "cooler": "reliable"},
    "multirole": {"shield": "balanced", "power": "balanced", "cooler": "balanced"},
    "cargo": {"shield": "durable", "power": "reliable", "cooler": "reliable"},
}

SHIP_ALIASES = {
    "drake corsair": "corsair",
    "corsair": "corsair",
    "shiv": "shiv",
    "grey's market shiv": "shiv",
    "greys market shiv": "shiv",
    "glsn shiv": "shiv",
    "cutlass blue": "cutlass blue",
    "drake cutlass blue": "cutlass blue",
    "arrow": "arrow",
    "anvil arrow": "arrow",
    "gladius": "gladius",
    "aegis gladius": "gladius",
    "sabre": "sabre",
    "aegis sabre": "sabre",
    "vanguard": "vanguard warden",
    "vanguard warden": "vanguard warden",
    "aegis vanguard warden": "vanguard warden",
}


def _norm(text: str | None) -> str:
    return " ".join((text or "").strip().lower().split())


def _fmt_num(value: float | int | None, digits: int = 0) -> str:
    if value is None:
        return "n/a"
    return f"{value:,.{digits}f}"


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


@dataclass(slots=True)
class SelectedItem:
    name: str
    size: int
    item_class: str
    grade: str | None = None
    count: int = 1
    component_class: str | None = None
    dps: float | None = None
    alpha: float | None = None

    def line(self) -> str:
        prefix = f"{self.count}x " if self.count > 1 else ""
        attrs = [f"Size {self.size}", f"Class {self.item_class}"]
        if self.component_class and self.component_class.lower() != self.item_class.lower():
            attrs.append(f"Type {self.component_class}")
        if self.grade:
            attrs.append(f"Grade {self.grade}")
        if self.dps is not None:
            attrs.append(f"{_fmt_num(self.dps, 0)} DPS each")
        if self.alpha is not None:
            attrs.append(f"{_fmt_num(self.alpha, 0)} alpha")
        return f"{prefix}{self.name} — {' • '.join(attrs)}"


class LoadoutEngine:
    def __init__(
        self,
        ship_db: dict[str, Any] | None = None,
        component_db: dict[str, Any] | None = None,
    ) -> None:
        self.ship_db = ship_db or _load_json(SHIP_DB_PATH)
        self.component_db = component_db or _load_json(COMPONENT_DB_PATH)

    def resolve_ship_key(self, ship_name: str) -> str | None:
        query = _norm(ship_name)
        if query in self.ship_db:
            return query
        if query in SHIP_ALIASES:
            return SHIP_ALIASES[query]

        for key, ship in self.ship_db.items():
            display = _norm(ship.get("display_name"))
            if query == display or query in display or display in query:
                return key
        return None

    def available_roles(self, ship: dict[str, Any]) -> list[str]:
        roles = ship.get("roles") or []
        return [r for r in roles if r in ROLE_DISPLAY]

    def normalize_role(self, ship: dict[str, Any], role: str | None) -> str:
        wanted = _norm(role).replace(" ", "_") if role else ""
        available = self.available_roles(ship)

        if wanted in ROLE_DISPLAY:
            return wanted

        default_role = ship.get("default_role")
        if isinstance(default_role, str) and default_role in ROLE_DISPLAY:
            return default_role

        if available:
            return available[0]

        return "multirole"

    def select_weapon(self, size: int, role: str) -> SelectedItem | None:
        style = ROLE_WEAPON_STYLE.get(role, "repeater")
        weapons = self.component_db.get("weapons", {})
        item = (weapons.get(style) or {}).get(str(size))

        if item is None and style != "repeater":
            item = (weapons.get("repeater") or {}).get(str(size))
        if item is None:
            item = (weapons.get("cannon") or {}).get(str(size))
        if item is None:
            return None

        return SelectedItem(
            name=item["name"],
            size=int(item["size"]),
            item_class=item["class"],
            grade=item.get("grade"),
            dps=item.get("dps"),
            alpha=item.get("alpha"),
        )

    def _profile_for_category(self, role: str, category: str) -> str:
        profile = ROLE_SYSTEM_PROFILE.get(role, ROLE_SYSTEM_PROFILE["multirole"])
        if category == "shields":
            return profile["shield"]
        if category == "power":
            return profile["power"]
        if category == "coolers":
            return profile["cooler"]
        return "balanced"

    def _resolve_profile_item(self, category: str, size: int, role: str) -> dict[str, Any] | None:
        by_size = (self.component_db.get("systems", {}).get(category, {}) or {}).get(str(size))
        if by_size is None:
            return None

        if "name" in by_size:
            return by_size

        wanted_profile = self._profile_for_category(role, category)
        return (
            by_size.get(wanted_profile)
            or by_size.get("balanced")
            or by_size.get("military")
            or by_size.get("reliable")
            or next(iter(by_size.values()), None)
        )

    def select_system(self, category: str, size: int, count: int, role: str) -> SelectedItem | None:
        item = self._resolve_profile_item(category, size, role)
        if item is None:
            return None
        return SelectedItem(
            name=item["name"],
            size=int(item["size"]),
            item_class=item["class"],
            grade=item.get("grade"),
            count=count,
            component_class=item.get("component_class"),
        )

    def select_missile(self, size: int, count: int) -> SelectedItem | None:
        item = (self.component_db.get("missiles", {}) or {}).get(str(size))
        if item is None:
            return None
        return SelectedItem(
            name=item["name"],
            size=int(item["size"]),
            item_class=item["class"],
            count=count,
        )

    def build(self, ship_name: str, role: str | None = None) -> LoadoutReport | None:
        ship_key = self.resolve_ship_key(ship_name)
        if not ship_key:
            return None

        ship = self.ship_db[ship_key]
        selected_role = self.normalize_role(ship, role)
        hardpoints = ship.get("hardpoints", {})
        stats = ship.get("stats", {})

        weapons: list[SelectedItem] = []
        total_dps = 0.0
        total_alpha = 0.0

        for slot in hardpoints.get("weapons", []):
            size = int(slot.get("size", 0))
            count = int(slot.get("count", 1))
            item = self.select_weapon(size, selected_role)
            if item:
                item.count = count
                weapons.append(item)
                if item.dps is not None:
                    total_dps += item.dps * count
                if item.alpha is not None:
                    total_alpha += item.alpha * count

        for slot in hardpoints.get("missiles", []):
            item = self.select_missile(int(slot.get("size", 0)), int(slot.get("count", 1)))
            if item:
                weapons.append(item)

        systems: list[SelectedItem] = []
        for category in ("shields", "power", "coolers"):
            counts = Counter()
            for slot in hardpoints.get(category, []):
                counts[int(slot.get("size", 0))] += int(slot.get("count", 1))
            for size, count in sorted(counts.items()):
                item = self.select_system(category, size, count, selected_role)
                if item:
                    systems.append(item)

        weapon_lines = [item.line() for item in weapons] or [
            "No weapon recommendation exists for this ship in the internal loadout database."
        ]
        system_lines = [item.line() for item in systems] or [
            "No system recommendation exists for this ship in the internal loadout database."
        ]

        perf_lines: list[str] = []
        if total_dps:
            perf_lines.append(f"Recommended weapon DPS: {_fmt_num(total_dps, 0)}")
        if total_alpha:
            perf_lines.append(f"Recommended alpha strike: {_fmt_num(total_alpha, 0)}")
        if stats.get("hull_hp") is not None:
            perf_lines.append(f"Hull HP: {_fmt_num(stats.get('hull_hp'), 0)}")
        if stats.get("shield_hp") is not None:
            perf_lines.append(f"Shield HP: {_fmt_num(stats.get('shield_hp'), 0)}")
        if stats.get("scm_speed") is not None or stats.get("max_speed") is not None:
            perf_lines.append(
                f"Speed: SCM {_fmt_num(stats.get('scm_speed'), 0)} m/s • Max {_fmt_num(stats.get('max_speed'), 0)} m/s"
            )
        if stats.get("cargo_scu") is not None:
            perf_lines.append(f"Cargo: {_fmt_num(stats.get('cargo_scu'), 0)} SCU")
        if stats.get("crew") is not None:
            perf_lines.append(f"Crew: {stats.get('crew')}")
        if not perf_lines:
            perf_lines.append("No performance stats are available in the internal loadout database.")

        hardpoint_notes: list[str] = []
        for key, label in (
            ("weapons", "Weapons"),
            ("missiles", "Missiles"),
            ("shields", "Shields"),
            ("power", "Power"),
            ("coolers", "Coolers"),
        ):
            slots = hardpoints.get(key, [])
            if not slots:
                continue
            parts = [f"{int(slot.get('count', 1))}x S{int(slot.get('size', 0))}" for slot in slots]
            hardpoint_notes.append(f"{label}: {' • '.join(parts)}")

        role_profile = ROLE_SYSTEM_PROFILE.get(selected_role, ROLE_SYSTEM_PROFILE["multirole"])

        notes = [
            f"Recommended role profile: {ROLE_DISPLAY[selected_role]}",
            f"System profile: shields={role_profile['shield']} • power={role_profile['power']} • cooling={role_profile['cooler']}",
            *hardpoint_notes,
            "Loadout v3.1 uses role-aware system profiles so S1 ships no longer recommend S2-only modules.",
        ]

        return LoadoutReport(
            ship_name=ship.get("display_name", ship_name),
            role=ROLE_DISPLAY[selected_role],
            manufacturer=ship.get("manufacturer", "Unknown Manufacturer"),
            weapons=weapon_lines,
            systems=system_lines,
            performance=perf_lines,
            notes=notes,
        )
