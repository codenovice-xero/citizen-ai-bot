from __future__ import annotations

from difflib import SequenceMatcher

from .models import AdvicePlan, LoadoutSuggestion, MiningSuggestion


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
        shields=[
            "Fast-recharge shield setup to recover between passes",
        ],
        power=[
            "Stable military-grade or competition power plant",
        ],
        coolers=[
            "High-efficiency cooler tuned for repeat attack runs",
        ],
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
        shields=[
            "Fast-recharge shield generator",
        ],
        power=[
            "Reliable military power plant",
        ],
        coolers=[
            "Balanced military cooler",
        ],
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
        shields=[
            "Military shield with good sustain",
        ],
        power=[
            "Military power plant",
        ],
        coolers=[
            "Efficient coolers to support stealth-friendly operation",
        ],
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
        shields=[
            "Two balanced shield generators",
        ],
        power=[
            "Reliable industrial or military power plant",
        ],
        coolers=[
            "Balanced coolers for multirole use",
        ],
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
        shields=[
            "Heavy shield sustain setup",
        ],
        power=[
            "Military-grade power plant for heavier weapon demand",
        ],
        coolers=[
            "High-capacity coolers",
        ],
        notes=[
            "Excels in PvE and crew-supported combat.",
            "Large profile means positioning matters.",
        ],
    ),
    LoadoutSuggestion(
        ship_name="C2 Hercules",
        role="Large Cargo Hauler",
        weapons=[
            "Defensive repeaters only; avoid building it as a brawler",
        ],
        shields=[
            "Heavy industrial shield sustain",
        ],
        power=[
            "High-stability industrial power plant",
        ],
        coolers=[
            "Reliable large-frame coolers",
        ],
        notes=[
            "Prioritize survivability and route planning over combat.",
            "Best value comes from cargo optimization, not weapons.",
        ],
    ),
    LoadoutSuggestion(
        ship_name="Mole",
        role="Group Mining Ship",
        weapons=[
            "Minimal defensive weapons",
        ],
        shields=[
            "Durable industrial shield setup",
        ],
        power=[
            "Industrial power plant",
        ],
        coolers=[
            "Industrial coolers",
        ],
        notes=[
            "Use crew coordination for best mining yield.",
            "Protect the ship instead of trying to fight everything.",
        ],
    ),
    LoadoutSuggestion(
        ship_name="Prospector",
        role="Solo Mining Ship",
        weapons=[
            "Minimal defensive weapons",
        ],
        shields=[
            "Balanced industrial shield setup",
        ],
        power=[
            "Industrial power plant",
        ],
        coolers=[
            "Industrial cooler",
        ],
        notes=[
            "Focus on mining performance and escape options.",
            "Best value comes from refining and disciplined cargo decisions.",
        ],
    ),
]


CURATED_MINING: list[MiningSuggestion] = [
    MiningSuggestion(
        ship_name="Prospector",
        modules=[
            "Stability-focused mining modules",
            "Extraction aids for volatile rocks",
        ],
        focus=[
            "Solo mining loops",
            "Refinery-friendly ores",
        ],
        notes=[
            "Avoid overcommitting to unstable rocks when solo.",
            "Plan refinery turnaround with hauling time in mind.",
        ],
    ),
    MiningSuggestion(
        ship_name="Mole",
        modules=[
            "Crew-synergy mining setup",
            "Support modules for difficult rocks",
        ],
        focus=[
            "High-yield multicrew mining",
            "Refinery batches with strong value density",
        ],
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


def get_loadout_suggestion(requested_ship: str) -> LoadoutSuggestion | None:
    requested_ship = (requested_ship or "").strip()
    if not requested_ship:
        return None

    exact = next((item for item in CURATED_LOADOUTS if _norm(item.ship_name) == _norm(requested_ship)), None)
    if exact:
        return exact

    best = max(CURATED_LOADOUTS, key=lambda item: _similarity(item.ship_name, requested_ship), default=None)
    if best and _similarity(best.ship_name, requested_ship) >= 0.82:
        return best

    return _build_dynamic_loadout(requested_ship)


def _build_dynamic_loadout(ship_name: str) -> LoadoutSuggestion:
    name = _norm(ship_name)

    if any(token in name for token in ["mole", "prospector", "arrastra", "orc", "mining"]):
        role = "Mining / Industrial"
        weapons = [
            "Minimal defensive weapons only",
            "Keep offense secondary to mining efficiency and escape options",
        ]
        shields = [
            "Industrial shield setup focused on survivability",
        ]
        power = [
            "Stable industrial power plant",
        ]
        coolers = [
            "Industrial coolers with steady heat handling",
        ]
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
        shields = [
            "High-sustain industrial or military shield setup",
        ]
        power = [
            "Reliable power plant for long-route consistency",
        ]
        coolers = [
            "Balanced coolers for travel and sustained operation",
        ]
        notes = [
            "Optimize for survival and route reliability, not kill potential.",
            "Stay conservative with investment size until supply and sell points are confirmed.",
            "Avoid obvious pirate lanes if profit difference is small.",
        ]
    elif any(token in name for token in ["vulture", "reclaimer", "salvage"]):
        role = "Salvage / Utility"
        weapons = [
            "Minimal self-defense package",
        ]
        shields = [
            "Sustain-focused shields for escape windows",
        ]
        power = [
            "Reliable industrial power plant",
        ]
        coolers = [
            "Balanced industrial coolers",
        ]
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
        shields = [
            "Fast-recharge shield setup",
        ]
        power = [
            "Responsive military or competition power plant",
        ]
        coolers = [
            "Efficient coolers for repeated attack passes",
        ]
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
        shields = [
            "Military shield configuration with strong sustain",
        ]
        power = [
            "Military-grade power plant",
        ]
        coolers = [
            "Performance coolers for sustained combat uptime",
        ]
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
        shields = [
            "Balanced shield setup",
        ]
        power = [
            "Reliable all-around power plant",
        ]
        coolers = [
            "Balanced coolers",
        ]
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
        bullets.extend(
            [
                "Stay low risk: deliveries, basic mercenary work, or starter bounties.",
                "Do not overinvest in commodity hauling at this bankroll.",
                "Loot discipline matters more than big-route dreams right now.",
            ]
        )
        title = "Low-Risk Credit Build"
        summary = "Grow capital steadily before taking on meaningful hauling or expensive refit choices."
    elif money_value < 250000:
        bullets.extend(
            [
                "You can start controlled legal hauling if your ship supports cargo.",
                "Mix bunker or bounty income with trading so one bad run does not stall progress.",
                "Use shorter, verified routes instead of chasing the absolute highest margin.",
            ]
        )
        title = "Balanced Mid-Tier Plan"
        summary = "You have enough credits to start making decisions, but not enough to absorb sloppy losses."
    else:
        bullets.extend(
            [
                "You can pursue larger legal trade routes with disciplined budgeting.",
                "Consider specialized gameplay loops that fit your ship: cargo, combat, or mining.",
                "Use your bankroll to reduce downtime and improve consistency, not just to gamble bigger.",
            ]
        )
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

    return AdvicePlan(
        title=title,
        summary=summary,
        bullets=bullets,
    )
