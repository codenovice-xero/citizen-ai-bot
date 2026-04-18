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
    item_id: int | None = None
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
    buy_price: float | None
    sell_price: float | None
    margin_per_unit: float | None
    estimated_profit: float | None
    confidence_note: str
    raw: dict[str, Any] = field(default_factory=dict)
