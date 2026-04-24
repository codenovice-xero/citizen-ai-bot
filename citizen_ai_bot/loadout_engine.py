from __future__ import annotations

import json
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
    "combat": {"shield": "military", "power": "military", "cooler": "military", "quantum": "combat"},
    "interceptor": {"shield": "fast-recharge", "power": "military", "cooler": "military", "quantum": "interceptor"},
    "heavy_fighter": {"shield": "military", "power": "military", "cooler": "military", "quantum": "combat"},
    "stealth": {"shield": "stealth", "power": "stealth", "cooler": "stealth", "quantum": "stealth"},
    "exploration": {"shield": "durable", "power": "reliable", "cooler": "reliable", "quantum": "durable"},
    "multirole": {"shield": "balanced", "power": "balanced", "cooler": "balanced", "quantum": "balanced"},
    "cargo": {"shield": "durable", "power": "reliable", "cooler": "reliable", "quantum": "durable"},
}

ROLE_META = {
    "combat": {
        "tier": "PvE/PvP general combat",
        "priority": "repeaters, military shields, military power, heat stability",
        "tactics": "Keep sustained pressure, avoid jousting, and disengage before shields collapse.",
    },
    "interceptor": {
        "tier": "fast-response PvP/intercept",
        "priority": "repeaters, fastest practical quantum drive, fast shield recovery",
        "tactics": "Use speed to dictate range, punish fleeing targets, and avoid prolonged nose-to-nose trades.",
    },
    "heavy_fighter": {
        "tier": "alpha-heavy brawler",
        "priority": "laser cannons, military shields, military power, burst damage",
        "tactics": "Trade deliberately, focus fire, and use higher alpha to punish predictable passes.",
    },
    "stealth": {
        "tier": "low-signature ambush",
        "priority": "distortion pressure, stealth systems, reduced signature profile",
        "tactics": "Choose fights carefully, break contact often, and avoid extended capacitor races.",
    },
    "exploration": {
        "tier": "range/survival expedition",
        "priority": "durable shields, reliable power, efficient quantum drive",
        "tactics": "Favor survivability and travel endurance over raw DPS.",
    },
    "multirole": {
        "tier": "balanced daily-driver",
        "priority": "balanced weapons, flexible shields, low-maintenance systems",
        "tactics": "Works across contracts, light hauling, and general org operations.",
    },
    "cargo": {
        "tier": "defensive hauling",
        "priority": "durable shields, reliable systems, escape-focused quantum drive",
        "tactics": "Survive long enough to spool, avoid combat commitment, and keep escorts nearby.",
    },
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
        if self.component_class:
            attrs.append(f"Type {self.component_class}")
        if self.grade:
            attrs.append(f"Grade {self.grade}")
        if self.dps is not None:
            attrs.append(f"{_fmt_num(self.dps, 0)} DPS each")
        if self.alpha is not None:
            attrs.append(f"{_fmt_num(self.alpha, 0)} alpha")
        return f"{prefix}{self.name} — {' • '.join(attrs)}"


class LoadoutEngine:
    def __init__(self, ship_db: dict[str, Any] | None = None, component_db: dict[str, Any] | None = None) -> None:
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
        return [role for role in ship.get("roles", []) if role in ROLE_DISPLAY]

    def normalize_role(self, ship: dict[str, Any], role: str | None) -> str:
        wanted = _norm(role).replace(" ", "_") if role else ""
        if wanted in ROLE_DISPLAY:
            return wanted
        default = ship.get("default_role")
        if isinstance(default, str) and default in ROLE_DISPLAY:
            return default
        roles = self.available_roles(ship)
        return roles[0] if roles else "multirole"

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
        mapping = {"shields": "shield", "power": "power", "coolers": "cooler", "quantum_drives": "quantum"}
        return profile.get(mapping.get(category, "shield"), "balanced")

    def select_system(self, category: str, size: int, count: int, role: str) -> SelectedItem | None:
        by_size = (self.component_db.get("systems", {}).get(category, {}) or {}).get(str(size))
        if not by_size:
            return None
        if "name" in by_size:
            item = by_size
        else:
            profile = self._profile_for_category(role, category)
            item = (
                by_size.get(profile)
                or by_size.get("balanced")
                or by_size.get("military")
                or by_size.get("durable")
                or next(iter(by_size.values()), None)
            )
        if not item:
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
        return SelectedItem(item["name"], int(item["size"]), item["class"], count=count)

    def _infer_quantum_size(self, stats: dict[str, Any]) -> int:
        crew = int(stats.get("crew") or 1)
        cargo = float(stats.get("cargo_scu") or 0)
        if crew >= 5 or cargo >= 96:
            return 3
        if crew >= 2 or cargo >= 24:
            return 2
        return 1

    def _score_lines(self, role: str, total_dps: float, total_alpha: float, stats: dict[str, Any]) -> list[str]:
        hull = float(stats.get("hull_hp") or 0)
        shield = float(stats.get("shield_hp") or 0)
        durability = hull + shield
        scm = float(stats.get("scm_speed") or 0)
        cargo = float(stats.get("cargo_scu") or 0)
        combat_score = (total_dps * 1.6) + (total_alpha * 2.2) + (durability / 120)
        mobility_score = scm + (total_dps / 20)
        utility_score = cargo + (durability / 4000)
        lines = [
            f"Meta Fit Score: {_fmt_num(combat_score if role in {'combat','heavy_fighter','stealth'} else mobility_score if role == 'interceptor' else utility_score, 0)}",
            f"Combat Score: {_fmt_num(combat_score, 0)}",
            f"Mobility Score: {_fmt_num(mobility_score, 0)}",
            f"Utility Score: {_fmt_num(utility_score, 0)}",
        ]
        if durability:
            lines.append(f"Durability Index: {_fmt_num(durability, 0)}")
        return lines

    def build(self, ship_name: str, role: str | None = None) -> LoadoutReport | None:
        ship_key = self.resolve_ship_key(ship_name)
        if not ship_key:
            return None

        ship = self.ship_db[ship_key]
        selected_role = self.normalize_role(ship, role)
        hardpoints = ship.get("hardpoints", {})
        stats = ship.get("stats", {})
        meta = ROLE_META[selected_role]

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
                total_dps += (item.dps or 0) * count
                total_alpha += (item.alpha or 0) * count

        for slot in hardpoints.get("missiles", []):
            item = self.select_missile(int(slot.get("size", 0)), int(slot.get("count", 1)))
            if item:
                weapons.append(item)

        systems: list[SelectedItem] = []
        for category in ("shields", "power", "coolers", "quantum_drives"):
            slots = hardpoints.get(category, [])
            if category == "quantum_drives" and not slots:
                slots = [{"size": self._infer_quantum_size(stats), "count": 1}]
            for slot in slots:
                item = self.select_system(category, int(slot.get("size", 0)), int(slot.get("count", 1)), selected_role)
                if item:
                    systems.append(item)

        performance = [
            f"Recommended weapon DPS: {_fmt_num(total_dps, 0)}",
            f"Recommended alpha strike: {_fmt_num(total_alpha, 0)}",
        ]
        if stats.get("hull_hp") is not None:
            performance.append(f"Hull HP: {_fmt_num(stats.get('hull_hp'), 0)}")
        if stats.get("shield_hp") is not None:
            performance.append(f"Shield HP: {_fmt_num(stats.get('shield_hp'), 0)}")
        if stats.get("scm_speed") is not None or stats.get("max_speed") is not None:
            performance.append(f"Speed: SCM {_fmt_num(stats.get('scm_speed'), 0)} m/s • Max {_fmt_num(stats.get('max_speed'), 0)} m/s")
        if stats.get("cargo_scu") is not None:
            performance.append(f"Cargo: {_fmt_num(stats.get('cargo_scu'), 0)} SCU")
        if stats.get("crew") is not None:
            performance.append(f"Crew: {stats.get('crew')}")
        performance.extend(self._score_lines(selected_role, total_dps, total_alpha, stats))

        profile = ROLE_SYSTEM_PROFILE[selected_role]
        notes = [
            f"Build Tier: {meta['tier']}",
            f"Recommended role profile: {ROLE_DISPLAY[selected_role]}",
            f"Build Priority: {meta['priority']}",
            f"Tactics: {meta['tactics']}",
            f"System profile: shields={profile['shield']} • power={profile['power']} • cooling={profile['cooler']} • quantum={profile['quantum']}",
            "Loadout v3: meta score, tactical role notes, quantum drive recommendation, Wiki ship data, and UEX enrichment hooks.",
        ]

        return LoadoutReport(
            ship_name=ship.get("display_name", ship_name),
            role=ROLE_DISPLAY[selected_role],
            manufacturer=ship.get("manufacturer", "Unknown Manufacturer"),
            weapons=[item.line() for item in weapons] or ["No weapon recommendation exists for this ship."],
            systems=[item.line() for item in systems] or ["No system recommendation exists for this ship."],
            performance=performance,
            notes=notes,
        )
