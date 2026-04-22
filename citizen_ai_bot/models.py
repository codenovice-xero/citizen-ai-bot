from dataclasses import dataclass, field


@dataclass
class LoadoutReport:
    ship_name: str
    role: str = ""
    manufacturer: str = ""
    weapons: list[str] = field(default_factory=list)
    systems: list[str] = field(default_factory=list)
    performance: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
