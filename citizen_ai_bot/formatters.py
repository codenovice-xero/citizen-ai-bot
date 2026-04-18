from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ItemMatch:
    name: str
    uuid: Any | None
    category: str | None = None
    company: str | None = None
    size: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ItemLocation:
    item_name: str
    location_name: str
    terminal_name: str | None = None
    buy_price: float | None = None
    sell_price: float | None = None
    scu: float | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class RouteSuggestion:
    commodity_name: str
    buy_location: str
    sell_location: str
    buy_price: float
    sell_price: float
    margin_per_unit: float
    estimated_profit: float | None = None
    confidence_note: str | None = None
    risk_label: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class AdvicePlan:
    title: str
    summary: str
    bullets: list[str]


@dataclass(slots=True)
class LoadoutSuggestion:
    ship_name: str
    role: str
    weapons: list[str]
    shields: list[str]
    power: list[str]
    coolers: list[str]
    notes: list[str]


@dataclass(slots=True)
class MiningSuggestion:
    ship_name: str
    modules: list[str]
    focus: list[str]
    notes: list[str]
