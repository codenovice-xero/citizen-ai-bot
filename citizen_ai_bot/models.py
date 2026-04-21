from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ItemMatch:
    name: str
    uuid: str | None = None
    category: str | None = None
    company: str | None = None
    size: str | None = None
    score: float = 0.0


@dataclass(slots=True)
class ItemLocation:
    location_name: str
    buy_price: float | None = None
    sell_price: float | None = None
    scu: float | None = None
    terminal_code: str | None = None
    terminal_name: str | None = None


@dataclass(slots=True)
class RouteSuggestion:
    commodity_name: str
    buy_location: str
    sell_location: str
    buy_price: float
    sell_price: float
    margin_per_unit: float
    estimated_profit: float
    risk_label: str = "Moderate"
    confidence_note: str | None = None


@dataclass(slots=True)
class AdvicePlan:
    title: str
    summary: str
    bullets: list[str] = field(default_factory=list)


@dataclass(slots=True)
class LoadoutComponent:
    name: str
    category: str
    size: str | None = None
    item_class: str | None = None
    grade: str | None = None
    group: str | None = None
    dps: float | None = None
    alpha_damage: float | None = None
    count: int = 1
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class LoadoutReport:
    ship_name: str
    role: str | None = None
    manufacturer: str | None = None
    hardpoints: list[str] = field(default_factory=list)
    weapons: list[str] = field(default_factory=list)
    systems: list[str] = field(default_factory=list)
    performance: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class MiningSuggestion:
    ship_name: str
    modules: list[str] = field(default_factory=list)
    focus: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
