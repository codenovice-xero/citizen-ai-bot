from __future__ import annotations

import logging
from collections import Counter
from difflib import SequenceMatcher
from typing import TYPE_CHECKING

from .models import AdvicePlan, LoadoutSuggestion, MiningSuggestion

if TYPE_CHECKING:
    from .wiki_client import WikiClient

log = logging.getLogger(__name__)


def _norm(value: str) -> str:
    return " ".join((value or "").strip().lower().split())


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, _norm(a), _norm(b)).ratio()


CURATED_LOADOUTS: list[LoadoutSuggestion] = [
    LoadoutSuggestion(
        ship_name="Shiv",
        role="Light Fighter / Hit-and-Run",
        weapons=[
            "Light laser repeaters for sustained pressure",
            "Fast projectile or ballistic nose option for burst damage",
        ],
        shields=["Fast-recharge shield setup to recover between passes"],
        power=["Stable military-grade or competition power plant"],
        coolers=["High-efficiency cooler tuned for repeat attack runs"],
        notes=[
            "Use speed and small profile to disengage often.",
            "Avoid long face-tank engagements against heavier ships.",
            "Best used for quick passes, pursuit, and opportunistic PvP.",
        ],
    ),
    LoadoutSuggestion(
        ship_name="Gladius",
        role="Light Fighter",
        weapons=[
            "Laser repeaters for easier pip tracking",
            "All-gimbal setup if you want consistency over burst",
        ],
        shields=["Fast-recharge shield generator"],
        power=["Reliable military power plant"],
        coolers=["Balanced military cooler"],
        notes=[
            "Great all-around dogfighter.",
            "Strong choice for pilots who want agility and clean weapon convergence.",
        ],
    ),
    LoadoutSuggestion(
        ship_name="Sabre Firebird",
        role="Stealth / Strike Fighter",
        weapons=[
            "Matched laser repeaters for sustained pressure",
            "Missile loadout focused on fast engagement openings",
        ],
        shields=["Military shield with good sustain"],
        power=["Military power plant"],
        coolers=["Efficient coolers to support stealth-friendly operation"],
        notes=[
            "Open fights on your terms and disengage before extended attrition.",
            "Best when flown aggressively but selectively.",
        ],
    ),
    LoadoutSuggestion(
        ship_name="Cutlass Black",
        role="Multirole",
        weapons=[
            "Laser repeaters for general PvE",
            "Missiles for burst opening pressure",
        ],
        shields=["Two balanced shield generators"],
        power=["Reliable industrial or military power plant"],
        coolers=["Balanced coolers for multirole use"],
        notes=[
            "Excellent starter multirole platform.",
            "Works well for cargo, bunkers, small-group combat, and ROC hauling.",
        ],
    ),
    LoadoutSuggestion(
        ship_name="Corsair",
        role="Heavy Multirole / PvE Gunship",
        weapons=[
            "High-alpha pilot weapons for PvE deletion",
            "Mixed sustained and burst setup if flying with turret support",
        ],
        shields=["Heavy shield sustain setup"],
        power=["Military-grade power plant for heavier weapon demand"],
        coolers=["High-capacity coolers"],
        notes=[
            "Excels in PvE and crew-supported combat.",
            "Large profile means positioning matters.",
        ],
    ),
    LoadoutSuggestion(
        ship_name="C2 Hercules",
        role="Large Cargo Hauler",
        weapons=["Defensive repeaters only; avoid building it as a brawler"],
        shields=["Heavy industrial shield sustain"],
        power=["High-stability industrial power plant"],
        coolers=["Reliable large-frame coolers"],
        notes=[
            "Prioritize survivability and route planning over combat.",
            "Best value comes from cargo optimization, not weapons.",
        ],
    ),
    LoadoutSuggestion(
        ship_name="Mole",
        role="Group Mining Ship",
        weapons=["Minimal defensive weapons"],
        shields=["Durable industrial shield setup"],
        power=["Industrial power plant"],
        coolers=["Industrial coolers"],
        notes=[
            "Use crew coordination for best mining yield.",
            "Protect the ship instead of trying to fight everything.",
        ],
    ),
    LoadoutSuggestion(
        ship_name="Prospector",
        role="Solo Mining Ship",
        weapons=["Minimal defensive weapons"],
        shields=["Balanced industrial shield setup"],
        power=["Industrial power plant"],
        coolers=["Industrial cooler"],
        notes=[
            "Focus on mining performance and escape options.",
            "Best value comes from refining and disciplined cargo decisions.",
        ],
    ),
]

CURATED_MINING: list[MiningSuggestion] = [
    MiningSuggestion(
        ship_name="Prospector",
        modules=["Stability-focused mining modules", "Extraction aids for volatile rocks"],
        focus=["Solo mining loops", "Refinery-friendly ores"],
        notes=[
            "Avoid overcommitting to unstable rocks when solo.",
            "Plan refinery turnaround with hauling time in mind.",
        ],
    ),
    MiningSuggestion(
        ship_name="Mole",
        modules=["Crew-synergy mining setup", "Support modules for difficult rocks"],
        focus=["High-yield multicrew mining", "Refinery batches with strong value density"],
        notes=[
            "Assign roles clearly: pilot, laser operator, support.",
            "Your profitability depends heavily on coordination.",
        ],
    ),
]

MISSION_GUIDE: dict[str, list[str]] = {
    "starter": [
        "Delivery missions for safe early reputation gains",
        "Low-risk mercenary bunkers with a dependable rifle and medpens",
        "Short legal hauling loops if you already have cargo space",
    ],
    "combat": [
        "Bounties for pilots with a reliable fighter and decent weapon convergence",
        "Bunker and mercenary missions for steady loot plus credits",
        "Group ERT-style content once you have survivability and repair discipline",
    ],
    "cargo": [
        "Legal commodity hauling with strict budget control",
        "Short hops first; expand route length after verifying supply and demand",
        "Use risk-aware routing instead of chasing only max theoretical margin",
    ],
    "mining": [
        "Prospector solo loops for flexible sessions",
        "MOLE multicrew mining for higher ceiling if your team is organized",
        "Refine selectively; not every load needs the same refinery plan",
    ],
}


def get_loadout_suggestion(
    requested_ship: str,
    wiki_enrichment: dict | None = None,
) -> LoadoutSuggestion | None:
    """Return a :class:`LoadoutSuggestion` for *requested_ship*.

    Resolution order:
    1. Exact match in ``CURATED_LOADOUTS`` (always wins — curated data is
       intentionally opinionated).
    2. Fuzzy match in ``CURATED_LOADOUTS`` (similarity ≥ 0.82).
    3. Dynamic fallback built from the ship name.

    If *wiki_enrichment* is provided (a dict returned by
    :func:`get_wiki_loadout`) the resulting suggestion is enriched with
    real hardpoint counts and performance stats before being returned.
    """
    requested_ship = (requested_ship or "").strip()
    if not requested_ship:
        return None

    exact = next((item for item in CURATED_LOADOUTS if _norm(item.ship_name) == _norm(requested_ship)), None)
    if exact:
        return _enrich_loadout(exact, wiki_enrichment) if wiki_enrichment else exact

    best = max(CURATED_LOADOUTS, key=lambda item: _similarity(item.ship_name, requested_ship), default=None)
    if best and _similarity(best.ship_name, requested_ship) >= 0.82:
        return _enrich_loadout(best, wiki_enrichment) if wiki_enrichment else best

    base = _build_dynamic_loadout(requested_ship)
    return _enrich_loadout(base, wiki_enrichment) if wiki_enrichment else base


async def get_wiki_loadout(
    ship_name: str,
    wiki: "WikiClient",
) -> dict | None:
    """Query the Star Citizen Wiki API for *ship_name* and return an enrichment dict.

    The returned dict contains:
    - ``hardpoints``: categorised hardpoint buckets from
      :meth:`WikiClient.get_hardpoints`
    - ``performance``: flat performance metrics from
      :meth:`WikiClient.get_performance`
    - ``ship_name``: the normalised name as returned by the API

    Returns ``None`` if the ship is not found or the API is unavailable,
    so callers can fall back to curated data transparently.
    """
    if not ship_name:
        return None
    try:
        ship_data = await wiki.get_ship(ship_name)
        if ship_data is None:
            return None

        hardpoints = wiki._extract_hardpoints(ship_data)
        performance = wiki._extract_performance(ship_data)

        return {
            "ship_name": str(ship_data.get("name") or ship_name),
            "hardpoints": hardpoints,
            "performance": performance,
        }
    except Exception as exc:
        log.warning("get_wiki_loadout failed for %r: %s", ship_name, exc)
        return None


def _classify_ship_type(ship_data: dict) -> str:
    """Determine a ship's role based on its performance stats.

    Classification priority (highest to lowest):
    - Transport: very high cargo (> 500 SCU)
    - Miner: high cargo (> 100 SCU), low agility, small crew
    - Dropship: high cargo (> 200 SCU), medium agility, crew 2+
    - Interceptor: very high max speed (> 1200 m/s), high agility, low cargo
    - Fighter: high agility (roll/pitch/yaw > 100), medium cargo (< 100 SCU), crew 1-2
    - Gunship: many weapon hardpoints, medium-high cargo, crew 2+
    - Exploration: medium cargo, medium speed, good shields
    - Multirole: fallback
    """
    performance: dict = ship_data.get("performance") or {}
    hardpoints: dict = ship_data.get("hardpoints") or {}

    cargo: float = float(performance.get("cargo_scu") or 0)
    max_speed: float = float(performance.get("max_speed") or 0)
    max_crew: int = int(performance.get("max_crew") or 1)
    shield_hp: float = float(performance.get("shield_hp") or 0)

    # Agility proxies — the Wiki API may expose these under different keys;
    # we read them from the raw performance dict if present.
    roll: float = float(performance.get("roll") or performance.get("roll_rate") or 0)
    pitch: float = float(performance.get("pitch") or performance.get("pitch_rate") or 0)
    yaw: float = float(performance.get("yaw") or performance.get("yaw_rate") or 0)
    high_agility: bool = any(v > 100 for v in (roll, pitch, yaw))

    weapon_count: int = len(hardpoints.get("weapons") or [])
    missile_count: int = len(hardpoints.get("missiles") or [])
    total_firepower: int = weapon_count + missile_count

    # --- Classification rules (order matters) ---
    if cargo > 500:
        return "Transport"

    if cargo > 200 and max_crew >= 2:
        return "Dropship"

    if cargo > 100 and max_crew <= 2 and not high_agility:
        return "Miner"

    if max_speed > 1200 and high_agility and cargo < 50:
        return "Interceptor"

    if high_agility and cargo < 100 and max_crew <= 2:
        return "Fighter"

    if total_firepower >= 6 and max_crew >= 2:
        return "Gunship"

    if 20 <= cargo <= 200 and shield_hp > 0 and max_speed > 0:
        return "Exploration"

    return "Multirole"


# ---------------------------------------------------------------------------
# Weapon type label helpers
# ---------------------------------------------------------------------------

_GENERIC_WEAPON_NAMES: frozenset[str] = frozenset({
    "weapon", "weapons", "gun", "guns", "laser", "cannon", "repeater",
    "ballistic", "energy", "hardpoint",
})

_GENERIC_COMPONENT_NAMES: frozenset[str] = frozenset({
    "shield", "shield generator", "shields",
    "power plant", "power", "powerplant",
    "cooler", "coolers",
})


def _clean_component_name(hp: dict) -> str:
    """Return a human-readable component label from a hardpoint entry dict.

    Filters out generic placeholder names (e.g. "Weapon", "Shield Generator")
    and constructs a richer label from size, class, type, and manufacturer
    fields when the raw name is too generic.
    """
    raw_name: str = str(hp.get("component_name") or "").strip()
    comp_class: str | None = hp.get("component_class")
    size: str | None = hp.get("size")
    manufacturer: str | None = hp.get("manufacturer")

    # Detect whether the raw name is too generic to be useful
    is_generic = _norm(raw_name) in _GENERIC_WEAPON_NAMES or _norm(raw_name) in _GENERIC_COMPONENT_NAMES

    if raw_name and not is_generic:
        # Good name — just annotate with size/class/manufacturer if missing
        parts: list[str] = []
        if size:
            parts.append(f"Size {size}")
        if comp_class:
            parts.append(f"Class {comp_class}")
        parts.append(raw_name)
        if manufacturer:
            parts.append(f"({manufacturer})")
        return " ".join(parts)

    # Build a synthetic name from available metadata
    parts = []
    if size:
        parts.append(f"Size {size}")
    if comp_class:
        parts.append(f"Class {comp_class}")
    # Use the raw name as a type hint even if generic, unless it's completely empty
    if raw_name:
        parts.append(raw_name.title())
    if manufacturer:
        parts.append(f"({manufacturer})")
    return " ".join(parts) if parts else "Unknown Component"


def _recommend_weapons(ship_type: str, hardpoints: dict) -> list[str]:
    """Return a list of weapon recommendation strings for *ship_type*.

    Uses the actual hardpoint data (sizes, counts) from the Wiki API when
    available, and falls back to role-based generic advice otherwise.
    """
    weapon_hps: list[dict] = hardpoints.get("weapons") or []
    missile_hps: list[dict] = hardpoints.get("missiles") or []
    recommendations: list[str] = []

    # --- Role-based primary weapon advice ---
    role_advice: dict[str, list[str]] = {
        "Fighter": [
            "Ballistic cannons for high burst alpha damage",
            "Laser repeaters for sustained pressure and easier pip tracking",
        ],
        "Interceptor": [
            "Light laser repeaters — low heat, high fire rate for fast passes",
            "Avoid heavy weapons; keep the loadout light for maximum speed",
        ],
        "Gunship": [
            "Mixed loadout: heavy cannons on pilot hardpoints for alpha damage",
            "Turret repeaters for sustained suppression",
            "Missile racks for opening-burst pressure",
        ],
        "Miner": [
            "Minimal defensive weapons only — prioritise mining laser modules",
            "Keep a light repeater for emergency deterrence",
        ],
        "Dropship": [
            "Defensive repeaters on turrets for escort deterrence",
            "Avoid heavy pilot weapons; cargo capacity is the priority",
        ],
        "Transport": [
            "Defensive repeaters only — do not build this as a brawler",
            "Turret coverage matters more than pilot weapon alpha",
        ],
        "Exploration": [
            "Balanced repeater setup for opportunistic PvE",
            "Missiles for burst damage against unexpected threats",
        ],
        "Multirole": [
            "General-purpose laser repeaters for flexible PvE",
            "Optional missile package for burst opening pressure",
        ],
    }
    for line in role_advice.get(ship_type, role_advice["Multirole"]):
        recommendations.append(line)

    # --- Actual Wiki hardpoint data ---
    if weapon_hps:
        spec_counts: Counter = Counter(
            _clean_component_name(hp) for hp in weapon_hps if _clean_component_name(hp)
        )
        if spec_counts:
            lines = [
                f"{cnt}× {spec}" if cnt > 1 else spec
                for spec, cnt in spec_counts.most_common(6)
            ]
            recommendations.append("Equipped: " + ", ".join(lines))
        else:
            sizes = sorted({str(hp["size"]) for hp in weapon_hps if hp.get("size")})
            if sizes:
                recommendations.append(
                    f"{len(weapon_hps)} weapon slot(s) — sizes {', '.join(sizes)}"
                )
            else:
                recommendations.append(f"{len(weapon_hps)} weapon hardpoint(s)")

    if missile_hps:
        spec_counts_m: Counter = Counter(
            _clean_component_name(hp) for hp in missile_hps if _clean_component_name(hp)
        )
        if spec_counts_m:
            lines_m = [
                f"{cnt}× {spec}" if cnt > 1 else spec
                for spec, cnt in spec_counts_m.most_common(4)
            ]
            recommendations.append("Missiles: " + ", ".join(lines_m))
        else:
            recommendations.append(f"{len(missile_hps)} missile hardpoint(s)")

    return recommendations


def _recommend_components(ship_type: str, performance: dict) -> dict[str, str]:
    """Return component recommendations keyed by slot type for *ship_type*.

    Values are short advisory strings that describe the ideal component
    class/priority for the ship's role.  Actual Wiki component data is
    overlaid by :func:`_enrich_loadout` after this function runs.
    """
    shield_hp: float = float(performance.get("shield_hp") or 0)
    shield_note = f" ({shield_hp:,.0f} HP from Wiki)" if shield_hp else ""

    recommendations: dict[str, dict[str, str]] = {
        "Fighter": {
            "shields": f"Class A fast-recharge shield — recover quickly between passes{shield_note}",
            "power": "Military or competition power plant — responsive output for combat bursts",
            "coolers": "Class A high-efficiency cooler — sustained heat from repeated weapon fire",
        },
        "Interceptor": {
            "shields": f"Lightweight fast-recharge shield — minimise mass{shield_note}",
            "power": "Competition power plant — prioritise speed over raw output",
            "coolers": "Efficient cooler — light repeaters still generate heat at high fire rates",
        },
        "Gunship": {
            "shields": f"Class A heavy shield — sustain in prolonged engagements{shield_note}",
            "power": "Military-grade power plant — heavy weapon demand requires stable output",
            "coolers": "High-capacity coolers — sustained turret and pilot weapon fire",
        },
        "Miner": {
            "shields": f"Industrial shield — survivability over combat performance{shield_note}",
            "power": "Industrial power plant — mining lasers draw significant power",
            "coolers": "Industrial cooler — steady heat from continuous mining laser use",
        },
        "Dropship": {
            "shields": f"Military shield with good sustain — protect the cargo bay{shield_note}",
            "power": "Reliable military power plant — balance weapons and life support",
            "coolers": "Balanced coolers for mixed combat and transit operation",
        },
        "Transport": {
            "shields": f"Heavy industrial shield — absorb hits while escaping{shield_note}",
            "power": "High-stability industrial power plant — cargo weight demands consistent output",
            "coolers": "Reliable large-frame coolers for long-haul operation",
        },
        "Exploration": {
            "shields": f"Military shield with strong sustain — unknown-space survivability{shield_note}",
            "power": "Reliable military power plant for extended range",
            "coolers": "Balanced coolers for mixed transit and combat readiness",
        },
        "Multirole": {
            "shields": f"Balanced shield setup{shield_note}",
            "power": "Reliable all-around power plant",
            "coolers": "Balanced coolers",
        },
    }
    return recommendations.get(ship_type, recommendations["Multirole"])


def _enrich_loadout(
    base: LoadoutSuggestion,
    wiki_data: dict,
) -> LoadoutSuggestion:
    """Return a new :class:`LoadoutSuggestion` built from data-driven recommendations.

    Replaces the old curated-text-plus-appended-Wiki approach with a fully
    data-driven pipeline:

    1. Classify the ship's role via :func:`_classify_ship_type`.
    2. Generate role-appropriate weapon recommendations via
       :func:`_recommend_weapons`, incorporating actual Wiki hardpoint specs.
    3. Generate role-appropriate component recommendations via
       :func:`_recommend_components`, incorporating actual Wiki component specs.
    4. Overlay real Wiki component names/sizes/classes/manufacturers on top of
       the advisory text so users see both the *why* and the *what*.
    5. Append performance metrics as a concise summary note.
    """
    hardpoints: dict = wiki_data.get("hardpoints") or {}
    performance: dict = wiki_data.get("performance") or {}
    wiki_ship_name: str = wiki_data.get("ship_name") or base.ship_name

    # ------------------------------------------------------------------
    # 1. Classify ship type from Wiki data
    # ------------------------------------------------------------------
    ship_type = _classify_ship_type({"performance": performance, "hardpoints": hardpoints})

    # Map ship type to a display role label (override curated role if we have
    # enough data to be confident about the classification)
    _type_to_role: dict[str, str] = {
        "Fighter": "Light Fighter",
        "Interceptor": "Interceptor",
        "Gunship": "Gunship",
        "Miner": "Mining / Industrial",
        "Dropship": "Dropship / Assault Transport",
        "Transport": "Heavy Transport",
        "Exploration": "Exploration / Multirole",
        "Multirole": "Multirole",
    }
    # Only override the curated role when we have real performance data to
    # base the classification on; otherwise keep the curated label.
    has_perf_data = bool(performance.get("max_speed") or performance.get("cargo_scu") or performance.get("max_crew"))
    role = _type_to_role.get(ship_type, base.role) if has_perf_data else base.role

    # ------------------------------------------------------------------
    # 2. Weapon recommendations (role-based + Wiki hardpoint specs)
    # ------------------------------------------------------------------
    weapons = _recommend_weapons(ship_type, hardpoints)

    # ------------------------------------------------------------------
    # 3. Component recommendations (role-based advisory text)
    # ------------------------------------------------------------------
    comp_recs = _recommend_components(ship_type, performance)

    # ------------------------------------------------------------------
    # Helper: build a detailed spec string for a single component entry,
    # filtering out generic placeholder names.
    # ------------------------------------------------------------------
    def _comp_spec(hp: dict) -> str:
        return _clean_component_name(hp)

    def _has_detail(hps: list[dict]) -> bool:
        return any(hp.get("size") or hp.get("component_name") or hp.get("component_class") for hp in hps)

    # ------------------------------------------------------------------
    # 4. Shields — advisory + Wiki specs
    # ------------------------------------------------------------------
    shields: list[str] = [comp_recs["shields"]]
    shield_hps = hardpoints.get("shields") or []
    if shield_hps:
        if _has_detail(shield_hps):
            specs = [_comp_spec(hp) for hp in shield_hps[:2] if _comp_spec(hp)]
            if specs:
                shields.append("Installed: " + ", ".join(specs))
            else:
                shields.append(f"{len(shield_hps)} shield slot(s) detected")
        else:
            shields.append(f"{len(shield_hps)} shield slot(s) detected")

    # ------------------------------------------------------------------
    # 5. Power — advisory + Wiki specs
    # ------------------------------------------------------------------
    power: list[str] = [comp_recs["power"]]
    power_hps = hardpoints.get("power") or []
    if power_hps:
        if _has_detail(power_hps):
            specs = [_comp_spec(hp) for hp in power_hps[:2] if _comp_spec(hp)]
            if specs:
                power.append("Installed: " + ", ".join(specs))
            else:
                power.append(f"{len(power_hps)} power slot(s) detected")
        else:
            power.append(f"{len(power_hps)} power slot(s) detected")

    # ------------------------------------------------------------------
    # 6. Coolers — advisory + Wiki specs
    # ------------------------------------------------------------------
    coolers: list[str] = [comp_recs["coolers"]]
    cooler_hps = hardpoints.get("coolers") or []
    if cooler_hps:
        if _has_detail(cooler_hps):
            specs = [_comp_spec(hp) for hp in cooler_hps[:2] if _comp_spec(hp)]
            if specs:
                coolers.append("Installed: " + ", ".join(specs))
            else:
                coolers.append(f"{len(cooler_hps)} cooler slot(s) detected")
        else:
            coolers.append(f"{len(cooler_hps)} cooler slot(s) detected")

    # ------------------------------------------------------------------
    # 7. Notes — performance metrics summary
    # ------------------------------------------------------------------
    notes: list[str] = []
    perf_lines: list[str] = []
    if performance.get("scm_speed"):
        perf_lines.append(f"SCM {performance['scm_speed']} m/s")
    if performance.get("max_speed"):
        perf_lines.append(f"max {performance['max_speed']} m/s")
    if performance.get("hull_hp"):
        perf_lines.append(f"hull {performance['hull_hp']:,} HP")
    if performance.get("cargo_scu"):
        perf_lines.append(f"cargo {performance['cargo_scu']} SCU")
    if performance.get("max_crew"):
        perf_lines.append(f"crew {performance['max_crew']}")
    if perf_lines:
        notes.append(f"Performance — {', '.join(perf_lines)}.")
    notes.append(f"Classified as **{ship_type}** based on Wiki stats ({wiki_ship_name}).")

    return LoadoutSuggestion(
        ship_name=base.ship_name,
        role=role,
        weapons=weapons,
        shields=shields,
        power=power,
        coolers=coolers,
        notes=notes,
    )



def _build_dynamic_loadout(ship_name: str) -> LoadoutSuggestion:
    name = _norm(ship_name)

    if any(token in name for token in ["mole", "prospector", "arrastra", "orc", "mining"]):
        role = "Mining / Industrial"
        weapons = [
            "Minimal defensive weapons only",
            "Keep offense secondary to mining efficiency and escape options",
        ]
        shields = ["Industrial shield setup focused on survivability"]
        power = ["Stable industrial power plant"]
        coolers = ["Industrial coolers with steady heat handling"]
        notes = [
            "Prioritize mining modules and escape planning over weapon upgrades.",
            "If solo, favor stability and lower-risk rocks over greed.",
            "If multicrew, assign mining roles clearly before each run.",
        ]
    elif any(token in name for token in ["c2", "m2", "a2", "freelancer", "raft", "taurus", "hull", "cargo", "hauler"]):
        role = "Cargo / Hauling"
        weapons = [
            "Defensive repeaters only",
            "Use weapons for deterrence, not prolonged fights",
        ]
        shields = ["High-sustain industrial or military shield setup"]
        power = ["Reliable power plant for long-route consistency"]
        coolers = ["Balanced coolers for travel and sustained operation"]
        notes = [
            "Optimize for survival and route reliability, not kill potential.",
            "Stay conservative with investment size until supply and sell points are confirmed.",
            "Avoid obvious pirate lanes if profit difference is small.",
        ]
    elif any(token in name for token in ["vulture", "reclaimer", "salvage"]):
        role = "Salvage / Utility"
        weapons = ["Minimal self-defense package"]
        shields = ["Sustain-focused shields for escape windows"]
        power = ["Reliable industrial power plant"]
        coolers = ["Balanced industrial coolers"]
        notes = [
            "Your money comes from staying on task, not taking fights.",
            "Choose routes and salvage zones you can exit cleanly.",
        ]
    elif any(token in name for token in ["gladius", "arrow", "shiv", "talon", "blade", "fighter", "interceptor"]):
        role = "Light Fighter / Interceptor"
        weapons = [
            "Matched laser repeaters for easier tracking and sustained pressure",
            "Optional ballistic burst setup if you prefer quick engagement windows",
        ]
        shields = ["Fast-recharge shield setup"]
        power = ["Responsive military or competition power plant"]
        coolers = ["Efficient coolers for repeated attack passes"]
        notes = [
            "Fight on your terms and disengage early when trades turn bad.",
            "Leverage speed, profile, and positioning instead of armor.",
            "Best used for hit-and-run, pursuit, and clean 1v1 execution.",
        ]
    elif any(token in name for token in ["sabre", "hornet", "scorpius", "vanguard", "heavy fighter"]):
        role = "Medium / Heavy Fighter"
        weapons = [
            "Sustained laser setup for general PvE",
            "High-alpha option if you prefer burst-heavy engagements",
        ]
        shields = ["Military shield configuration with strong sustain"]
        power = ["Military-grade power plant"]
        coolers = ["Performance coolers for sustained combat uptime"]
        notes = [
            "Built to stay in fights longer than light fighters.",
            "Use your durability and firepower advantage deliberately.",
            "Great for bounties, escorts, and small-group combat roles.",
        ]
    else:
        role = "Multirole"
        weapons = [
            "General-purpose laser repeaters",
            "Flexible missile package if the ship supports it",
        ]
        shields = ["Balanced shield setup"]
        power = ["Reliable all-around power plant"]
        coolers = ["Balanced coolers"]
        notes = [
            "Use a balanced setup until you specialize the ship's job.",
            "Choose upgrades that reinforce the ship's strongest role first.",
            "If uncertain, prioritize survivability and sustained uptime.",
        ]

    notes.append("This is a dynamic fallback recommendation generated because no curated ship-specific entry was found.")

    return LoadoutSuggestion(
        ship_name=ship_name.strip().title(),
        role=role,
        weapons=weapons,
        shields=shields,
        power=power,
        coolers=coolers,
        notes=notes,
    )


def get_mining_suggestion(requested_ship: str) -> MiningSuggestion | None:
    requested_ship = (requested_ship or "").strip()
    if not requested_ship:
        return None

    exact = next((item for item in CURATED_MINING if _norm(item.ship_name) == _norm(requested_ship)), None)
    if exact:
        return exact

    best = max(CURATED_MINING, key=lambda item: _similarity(item.ship_name, requested_ship), default=None)
    if best and _similarity(best.ship_name, requested_ship) >= 0.82:
        return best

    if any(token in _norm(requested_ship) for token in ["mole", "prospector", "arrastra", "mining"]):
        return MiningSuggestion(
            ship_name=requested_ship.strip().title(),
            modules=[
                "Stability-oriented mining modules",
                "Support modules matched to the rock difficulty you usually target",
            ],
            focus=[
                "Consistent yield over risky greed plays",
                "Route planning that includes refinery turnaround",
            ],
            notes=[
                "This is a dynamic fallback suggestion generated from the ship name.",
                "Tune your modules around whether you mine solo or with crew.",
            ],
        )

    return None


def build_advice_plan(money: int | float | None = None, ship: str | None = None) -> AdvicePlan:
    money_value = float(money or 0)
    ship_name = (ship or "").strip()
    bullets: list[str] = []

    if money_value < 50000:
        bullets.extend([
            "Stay low risk: deliveries, basic mercenary work, or starter bounties.",
            "Do not overinvest in commodity hauling at this bankroll.",
            "Loot discipline matters more than big-route dreams right now.",
        ])
        title = "Low-Risk Credit Build"
        summary = "Grow capital steadily before taking on meaningful hauling or expensive refit choices."
    elif money_value < 250000:
        bullets.extend([
            "You can start controlled legal hauling if your ship supports cargo.",
            "Mix bunker or bounty income with trading so one bad run does not stall progress.",
            "Use shorter, verified routes instead of chasing the absolute highest margin.",
        ])
        title = "Balanced Mid-Tier Plan"
        summary = "You have enough credits to start making decisions, but not enough to absorb sloppy losses."
    else:
        bullets.extend([
            "You can pursue larger legal trade routes with disciplined budgeting.",
            "Consider specialized gameplay loops that fit your ship: cargo, combat, or mining.",
            "Use your bankroll to reduce downtime and improve consistency, not just to gamble bigger.",
        ])
        title = "Expansion Plan"
        summary = "You have enough capital to optimize your gameplay loop around efficiency instead of pure survival."

    if ship_name:
        loadout = get_loadout_suggestion(ship_name)
        bullets.append(
            f"Ship focus: {ship_name} is best treated as a {loadout.role.lower()} platform."
            if loadout
            else f"Ship focus: build around what {ship_name} does best."
        )
        if loadout and "cargo" in loadout.role.lower():
            bullets.append("Pair your route choice with risk discipline; safe consistency often beats theoretical max profit.")
        elif loadout and "fighter" in loadout.role.lower():
            bullets.append("Use combat income or escort work to support your next ship or module upgrades.")
        elif loadout and "mining" in loadout.role.lower():
            bullets.append("Mining profits improve dramatically when you plan extraction, transport, and refining as one loop.")

    return AdvicePlan(title=title, summary=summary, bullets=bullets)
