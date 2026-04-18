from __future__ import annotations

SHIP_CARGO_SCU = {
    "c2 hercules": 696,
    "m2 hercules": 522,
    "caterpillar": 576,
    "freelancer max": 120,
    "constellation taurus": 174,
    "cutlass black": 46,
    "raft": 96,
    "starlancer max": 224,
    "nomad": 24,
    "vulture": 12,
    "hull a": 64,
}

LOADOUTS = {
    "sabre firebird": {
        "role": "Stealth strike / hit-and-run",
        "weapons": ["4x laser repeaters for sustained PvP pressure", "swap to laser cannons for higher alpha at range"],
        "shields": ["prioritize fast-regening military-grade options when available"],
        "power": ["use a dependable power plant that supports full weapon capacitor draw"],
        "coolers": ["run coolers that support stealth windows and repeated attack passes"],
        "notes": [
            "Lean into burst engagements instead of prolonged face-tanking.",
            "Keep EM/IR down and disengage early when outnumbered.",
        ],
    },
    "cutlass black": {
        "role": "Flexible PvE / cargo / light combat",
        "weapons": ["mixed laser repeater setup for forgiving sustained damage", "ballistics for short aggressive sorties"],
        "shields": ["balanced shield choices are usually better than extreme niche picks"],
        "power": ["keep enough headroom for repeaters, QT, and utility"],
        "coolers": ["reliable mid-tier coolers are fine for most PvE"],
        "notes": [
            "Great ship for general money-making and mercenary loops.",
            "Use the cargo bay flexibility to pivot between trade, salvage, and bunker support.",
        ],
    },
    "c2 hercules": {
        "role": "Large-scale hauling",
        "weapons": ["defensive turrets matter more than pilot DPS"],
        "shields": ["maximize survivability and QT consistency"],
        "power": ["stable military/industrial power options recommended"],
        "coolers": ["durability over niche combat tuning"],
        "notes": [
            "Avoid unnecessary risk on margin-thin routes.",
            "A big cargo ship wins by uptime and survival, not dogfighting.",
        ],
    },
}

MINING = {
    "prospector": {
        "modules": ["Rieger or surge-style instability control", "focus modules that help break mid-hardness rocks"],
        "focus": ["solo ROC support or compact rock routes", "refine high-value ore instead of dumping low-tier loads"],
        "notes": [
            "Skip marginal rocks when time-to-break is poor.",
            "Prioritize stable extraction over overloading the bag.",
        ],
    },
    "mole": {
        "modules": ["coordinate lasers for main/support roles", "use loadouts tuned for fracture plus stability"],
        "focus": ["multi-crew ore extraction", "higher-yield organized mining loops"],
        "notes": [
            "The MOLE shines with coordination, not solo inefficiency.",
            "Use one operator for stability support when cracking larger rocks.",
        ],
    },
    "golem": {
        "modules": ["run control-focused modules first", "then tune for throughput once stable"],
        "focus": ["efficient rock cycling", "crew-safe extractions"],
        "notes": [
            "Start conservative until you know how the current patch feels.",
            "Avoid greed breaks that create long recovery time.",
        ],
    },
}

MISSION_ADVICE = {
    "bounty": [
        "Great when you want fast action and already have a capable combat ship.",
        "Stack legal contracts in areas with tight travel distances.",
        "Use a ship you can rearm quickly to keep downtime low.",
    ],
    "cargo": [
        "Best when you have enough capital to fill meaningful SCU.",
        "Risk management matters more than theoretical max margin.",
        "Run repeatable safe loops first, then branch into higher-profit lanes.",
    ],
    "mining": [
        "Strong if you know extraction and refinery timing.",
        "Mining wins when you are disciplined about what rocks you ignore.",
        "Use refining to lift value instead of panic-selling raw loads.",
    ],
    "salvage": [
        "Excellent for steady solo income and low-stress sessions.",
        "Chain efficient salvage loops and keep travel minimized.",
        "Sell consistently instead of overcommitting to risky holds.",
    ],
}
