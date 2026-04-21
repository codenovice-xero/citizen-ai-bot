from __future__ import annotations

import time
from typing import Any

from .models import AdvicePlan, ItemLocation, ItemMatch, LoadoutSuggestion, MiningSuggestion, RouteSuggestion
from .static_data import (
    MISSION_GUIDE,
    build_advice_plan,
    get_wiki_loadout,
    get_loadout_suggestion,
    get_mining_suggestion,
)
from .uex_client import UEXClient
from .wiki_client import WikiClient
from .utils import clamp, fuzzy_score


class StarCitizenService:
    def __init__(self, client: UEXClient) -> None:
        self.client = client
        self.wiki = WikiClient()
        self._items_prices_all_cache: list[dict[str, Any]] = []
        self._items_prices_all_cache_ts: float = 0.0
        self._items_prices_all_cache_ttl: int = 60 * 30
        self._commodity_snapshots: dict[str, tuple[float, list[dict[str, Any]]]] = {}
        self._commodity_snapshot_ttl: int = 60 * 20

    async def health_status(self) -> dict[str, bool]:
        uex_ok = False
        wiki_ok = False

        try:
            uex_ok = await self.client.ping()
        except Exception:
            uex_ok = False

        try:
            wiki_ok = await self.wiki.ping()
        except Exception:
            wiki_ok = False

        return {"uex": uex_ok, "wiki": wiki_ok}

    @staticmethod
    def _extract_records(payload: dict[str, Any]) -> list[dict[str, Any]]:
        if isinstance(payload.get("data"), list):
            return payload["data"]
        if isinstance(payload.get("data"), dict):
            nested = payload["data"]
            if isinstance(nested.get("data"), list):
                return nested["data"]
        for value in payload.values():
            if isinstance(value, list) and (not value or isinstance(value[0], dict)):
                return value
        return []

    async def _get_items_prices_all(self) -> list[dict[str, Any]]:
        now = time.time()
        if self._items_prices_all_cache and (now - self._items_prices_all_cache_ts) < self._items_prices_all_cache_ttl:
            return self._items_prices_all_cache

        payload = await self.client.get("/items_prices_all")
        records = self._extract_records(payload)
        self._items_prices_all_cache = records
        self._items_prices_all_cache_ts = now
        return records

    async def search_items(self, query: str, limit: int = 8) -> list[ItemMatch]:
        records = await self._get_items_prices_all()
        query = query.strip().lower()
        if not query:
            return []

        seen: dict[Any, dict[str, Any]] = {}
        for record in records:
            item_name = str(record.get("item_name", "") or "").strip()
            if not item_name:
                continue

            item_name_lower = item_name.lower()
            contains_match = query in item_name_lower
            score = fuzzy_score(query, item_name_lower)
            if not contains_match and score < 0.45:
                continue

            item_id = record.get("id_item")
            dedupe_key = item_id if item_id is not None else item_name_lower
            effective_score = 1.0 if contains_match else score

            if dedupe_key not in seen or effective_score > seen[dedupe_key]["score"]:
                seen[dedupe_key] = {
                    "id_item": item_id,
                    "item_name": item_name,
                    "category": record.get("section") or record.get("category"),
                    "company_name": record.get("company_name"),
                    "size": record.get("size"),
                    "score": effective_score,
                    "raw": record,
                }

        ranked = sorted(seen.values(), key=lambda r: r["score"], reverse=True)
        return [
            ItemMatch(
                name=str(record.get("item_name", "Unknown Item")),
                uuid=record.get("id_item"),
                category=str(record.get("category", "")) or None,
                company=str(record.get("company_name", "")) or None,
                size=str(record.get("size", "")) or None,
                raw=record.get("raw", record),
            )
            for record in ranked[:limit]
        ]

    async def get_item_locations(self, item_name: str, limit: int = 10) -> tuple[list[ItemMatch], list[ItemLocation]]:
        item_matches = await self.search_items(item_name, limit=5)
        if not item_matches:
            return [], []

        best_match = item_matches[0]
        item_id = best_match.uuid
        if item_id is None:
            return item_matches, []

        try:
            payload = await self.client.get("/items_prices", params={"id_item": item_id})
            records = self._extract_records(payload)
        except Exception:
            records = []

        locations: list[ItemLocation] = []
        for record in records:
            locations.append(
                ItemLocation(
                    item_name=str(record.get("item_name", "") or best_match.name),
                    location_name=self._location_label(record),
                    terminal_name=record.get("terminal_name") or record.get("store_name"),
                    buy_price=self._safe_float(record.get("price_buy") or record.get("buy_price")),
                    sell_price=self._safe_float(record.get("price_sell") or record.get("sell_price")),
                    scu=self._safe_float(record.get("scu") or record.get("volume")),
                    raw=record,
                )
            )

        def location_sort_key(loc: ItemLocation) -> tuple[int, float]:
            buy_price = loc.buy_price if loc.buy_price is not None else float("inf")
            has_terminal = 0 if loc.terminal_name else 1
            return (has_terminal, buy_price)

        return item_matches, sorted(locations, key=location_sort_key)[:limit]

    async def _get_commodity_prices(self, commodity_name: str) -> list[dict[str, Any]]:
        now = time.time()
        key = commodity_name.strip().lower()
        cached = self._commodity_snapshots.get(key)
        if cached and (now - cached[0]) < self._commodity_snapshot_ttl:
            return cached[1]

        payload = await self.client.get("/commodities_prices", params={"commodity_name": commodity_name})
        records = self._extract_records(payload)
        self._commodity_snapshots[key] = (now, records)
        return records

    def estimate_route_risk(self, buy_label: str, sell_label: str, legal_only: bool = False) -> tuple[str, list[str]]:
        text = f"{buy_label} {sell_label}".lower()
        score = 0.2
        notes: list[str] = []

        if any(word in text for word in ["outpost", "moon"]):
            score += 0.18
            notes.append("Outpost and moon stops are more exposed than major city terminals.")
        if any(word in text for word in ["grim hex", "pyro"]):
            score += 0.35
            notes.append("Location has a stronger PvP / piracy reputation.")
        if any(word in text for word in ["station", "area18", "lorville", "new babbage", "orison"]):
            score -= 0.08
            notes.append("Major hub logistics are usually more predictable.")
        if not legal_only:
            score += 0.12
            notes.append("Open commodity filtering can include riskier lanes.")

        score = clamp(score, 0.05, 0.95)
        if score < 0.28:
            label = "Low"
        elif score < 0.48:
            label = "Moderate"
        elif score < 0.70:
            label = "High"
        else:
            label = "Extreme"
        return label, notes

    async def list_trade_routes(
        self,
        commodity_name: str,
        from_location: str | None = None,
        budget: float | None = None,
        cargo_scu: float | None = None,
        legal_only: bool = False,
        limit: int = 5,
    ) -> list[RouteSuggestion]:
        records = await self._get_commodity_prices(commodity_name)
        if not records:
            return []

        relevant: list[dict[str, Any]] = []
        for record in records:
            name = str(record.get("commodity_name") or "")
            if fuzzy_score(commodity_name, name) < 0.72:
                continue
            if from_location:
                candidate = " ".join(
                    str(record.get(key) or "")
                    for key in ("terminal_name", "city_name", "outpost_name", "space_station_name", "planet_name", "moon_name")
                )
                if fuzzy_score(from_location, candidate) < 0.55:
                    continue
            if legal_only and str(record.get("is_illegal") or "0") not in ("0", "False", "false", ""):
                continue
            relevant.append(record)

        if not relevant:
            return []

        buy_candidates = [r for r in relevant if (self._safe_float(r.get("price_buy")) or 0) > 0]
        sell_candidates = [r for r in relevant if (self._safe_float(r.get("price_sell")) or 0) > 0]
        if not buy_candidates or not sell_candidates:
            return []

        suggestions: list[RouteSuggestion] = []
        for buy_row in buy_candidates:
            buy_price = self._safe_float(buy_row.get("price_buy"))
            if buy_price is None or buy_price <= 0:
                continue
            for sell_row in sell_candidates:
                sell_price = self._safe_float(sell_row.get("price_sell"))
                if sell_price is None or sell_price <= buy_price:
                    continue
                if self._location_label(buy_row) == self._location_label(sell_row):
                    continue

                units = cargo_scu or self._safe_float(buy_row.get("scu_buy") or buy_row.get("scu_buy_avg") or 0) or 0
                if budget and buy_price > 0:
                    affordable_units = budget / buy_price
                    units = min(units or affordable_units, affordable_units)
                estimated_profit = (sell_price - buy_price) * units if units else None

                risk_label, _ = self.estimate_route_risk(
                    self._location_label(buy_row), self._location_label(sell_row), legal_only=legal_only
                )
                suggestions.append(
                    RouteSuggestion(
                        commodity_name=str(buy_row.get("commodity_name") or commodity_name),
                        buy_location=self._location_label(buy_row),
                        sell_location=self._location_label(sell_row),
                        buy_price=buy_price,
                        sell_price=sell_price,
                        margin_per_unit=sell_price - buy_price,
                        estimated_profit=estimated_profit,
                        confidence_note="Calculated from live UEX commodity prices. Data is community-maintained and can shift quickly.",
                        risk_label=risk_label,
                        raw={"buy": buy_row, "sell": sell_row},
                    )
                )

        suggestions.sort(key=lambda s: (s.estimated_profit or 0, s.margin_per_unit), reverse=True)

        deduped: list[RouteSuggestion] = []
        seen: set[tuple[str, str]] = set()
        for suggestion in suggestions:
            key = (suggestion.buy_location, suggestion.sell_location)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(suggestion)
            if len(deduped) >= limit:
                break
        return deduped

    async def suggest_trade_route(
        self,
        commodity_name: str,
        from_location: str | None = None,
        budget: float | None = None,
        cargo_scu: float | None = None,
        legal_only: bool = False,
    ) -> RouteSuggestion | None:
        routes = await self.list_trade_routes(
            commodity_name=commodity_name,
            from_location=from_location,
            budget=budget,
            cargo_scu=cargo_scu,
            legal_only=legal_only,
            limit=1,
        )
        return routes[0] if routes else None

    def advice_for_player(self, money: float | None, ship: str | None, risk_tolerance: str | None) -> AdvicePlan:
        return build_advice_plan(money=money, ship=ship, risk_tolerance=risk_tolerance)

    async def suggest_loadout(self, ship_name: str) -> LoadoutSuggestion | None:
        """Return a loadout suggestion for *ship_name*.

        Attempts to enrich the curated suggestion with live hardpoint and
        performance data from the Star Citizen Wiki API.  Falls back
        gracefully to the curated / dynamic suggestion if the API is
        unavailable.
        """
        wiki_data = await get_wiki_loadout(ship_name, self.wiki)
        return get_loadout_suggestion(ship_name, wiki_enrichment=wiki_data)

    def suggest_mining(self, ship_name: str) -> MiningSuggestion | None:
        return get_mining_suggestion(ship_name)

    def mission_plan(self, mission_type: str) -> AdvicePlan:
        mission_type = mission_type.strip().lower()
        best_key = None
        best_score = 0.0
        for key in MISSION_GUIDE:
            score = fuzzy_score(mission_type, key)
            if score > best_score:
                best_key = key
                best_score = score

        if not best_key:
            return AdvicePlan(
                title="Mission Planning",
                summary="Use mission types like combat, cargo, mining, or starter.",
                bullets=["Choose the loop that matches your ship and bankroll."],
            )

        return AdvicePlan(
            title=f"{best_key.title()} Progression",
            summary=f"Guidance for {best_key}-focused sessions.",
            bullets=MISSION_GUIDE[best_key],
        )

    async def price_snapshot(self, commodity_name: str) -> dict[str, Any] | None:
        routes = await self.list_trade_routes(commodity_name=commodity_name, limit=3)
        if not routes:
            return None
        margins = [r.margin_per_unit for r in routes]
        avg_margin = sum(margins) / len(margins)
        return {
            "commodity": routes[0].commodity_name,
            "best_margin": max(margins),
            "avg_margin": avg_margin,
            "top_route": routes[0],
            "snapshot_note": "Historical trend storage is not implemented yet; this is a live market snapshot.",
        }

    def plan_operation(self, event: str) -> AdvicePlan:
        event = event.strip() or "general op"
        bullets = [
            "Set rally point and fallback point before launch.",
            "Assign pilot, ground lead, medic, cargo/security, and extraction roles.",
            "Confirm medpens, ammo, tractor tools, and storage space before departure.",
            "Plan exfil first so the team does not improvise under pressure.",
        ]
        return AdvicePlan(title=f"Operation Plan: {event}", summary="Simple org-ready prep checklist.", bullets=bullets)

    @staticmethod
    def _location_label(record: dict[str, Any]) -> str:
        parts = [
            record.get("terminal_name"),
            record.get("city_name"),
            record.get("outpost_name"),
            record.get("space_station_name"),
            record.get("moon_name"),
            record.get("planet_name"),
            record.get("star_system_name"),
        ]
        cleaned = [str(part) for part in parts if part not in (None, "")]
        return " • ".join(cleaned) if cleaned else "Unknown Location"

    @staticmethod
    def _safe_float(value: Any) -> float | None:
        try:
            if value in (None, ""):
                return None
            return float(value)
        except (TypeError, ValueError):
            return None
