from __future__ import annotations

import time
from typing import Any

from .models import ItemLocation, ItemMatch, RouteSuggestion
from .uex_client import UEXClient
from .utils import fuzzy_score


class StarCitizenService:
    _ITEM_PRICE_CACHE_TTL_SECONDS = 60 * 30

    def __init__(self, client: UEXClient) -> None:
        self.client = client
        self._items_prices_all_cache: list[dict[str, Any]] = []
        self._items_prices_all_cache_at: float = 0.0

    @staticmethod
    def _extract_records(payload: dict[str, Any]) -> list[dict[str, Any]]:
        if isinstance(payload.get("data"), list):
            return payload["data"]
        if isinstance(payload.get("data"), dict):
            nested = payload["data"]
            if isinstance(nested.get("data"), list):
                return nested["data"]
        for value in payload.values():
            if isinstance(value, list) and value and isinstance(value[0], dict):
                return value
        return []

    async def _get_items_prices_all(self, force_refresh: bool = False) -> list[dict[str, Any]]:
        now = time.time()
        cache_is_fresh = (now - self._items_prices_all_cache_at) < self._ITEM_PRICE_CACHE_TTL_SECONDS
        if self._items_prices_all_cache and cache_is_fresh and not force_refresh:
            return self._items_prices_all_cache

        payload = await self.client.get("/items_prices_all")
        records = self._extract_records(payload)
        self._items_prices_all_cache = records
        self._items_prices_all_cache_at = now
        return records

    async def search_items(self, query: str, limit: int = 8) -> list[ItemMatch]:
        records = await self._get_items_prices_all()
        normalized_query = query.strip().lower()

        deduped: dict[int, dict[str, Any]] = {}
        ranked_candidates: list[tuple[float, dict[str, Any]]] = []

        for record in records:
            item_name = str(record.get("item_name") or "").strip()
            if not item_name:
                continue

            item_id = record.get("id_item")
            try:
                item_id_int = int(item_id)
            except (TypeError, ValueError):
                continue

            score = max(
                fuzzy_score(query, item_name),
                1.0 if normalized_query and normalized_query in item_name.lower() else 0.0,
            )
            if score < 0.45:
                continue

            existing = deduped.get(item_id_int)
            if existing is None or score > existing.get("_score", 0.0):
                enriched = dict(record)
                enriched["_score"] = score
                deduped[item_id_int] = enriched

        for record in deduped.values():
            ranked_candidates.append((float(record.get("_score", 0.0)), record))

        ranked_candidates.sort(key=lambda pair: pair[0], reverse=True)

        results: list[ItemMatch] = []
        for _, record in ranked_candidates[:limit]:
            results.append(
                ItemMatch(
                    name=str(record.get("item_name", "Unknown Item")),
                    uuid=record.get("uuid") or record.get("item_uuid"),
                    category=str(record.get("section", "")) or None,
                    company=str(record.get("company_name", "")) or None,
                    size=str(record.get("size", "")) or None,
                    item_id=int(record["id_item"]),
                    raw=record,
                )
            )
        return results

    async def get_item_locations(self, item_name: str, limit: int = 10) -> tuple[list[ItemMatch], list[ItemLocation]]:
        item_matches = await self.search_items(item_name, limit=5)
        if not item_matches:
            return [], []

        best_match = item_matches[0]
        if best_match.item_id is None:
            return item_matches, []

        payload = await self.client.get("/items_prices", params={"id_item": best_match.item_id})
        records = self._extract_records(payload)

        locations: list[ItemLocation] = []
        seen_keys: set[tuple[str, float | None, float | None]] = set()
        for record in records:
            item_id = record.get("id_item")
            try:
                if int(item_id) != best_match.item_id:
                    continue
            except (TypeError, ValueError):
                continue

            location_name = self._compose_location_name(record)
            buy_price = self._safe_float(record.get("price_buy") or record.get("buy_price"))
            sell_price = self._safe_float(record.get("price_sell") or record.get("sell_price"))
            dedupe_key = (location_name, buy_price, sell_price)
            if dedupe_key in seen_keys:
                continue
            seen_keys.add(dedupe_key)

            locations.append(
                ItemLocation(
                    item_name=str(record.get("item_name") or best_match.name),
                    location_name=location_name,
                    terminal_name=record.get("terminal_name"),
                    buy_price=buy_price,
                    sell_price=sell_price,
                    scu=self._safe_float(record.get("scu") or record.get("volume")),
                    raw=record,
                )
            )

        locations.sort(
            key=lambda loc: (
                loc.buy_price is None,
                loc.buy_price if loc.buy_price is not None else float("inf"),
                loc.location_name.lower(),
            )
        )
        return item_matches, locations[:limit]

    async def search_commodity(self, commodity_name: str, limit: int = 10) -> list[ItemMatch]:
        items = await self.search_items(commodity_name, limit=20)
        filtered = [
            item for item in items
            if (item.category and "commodity" in item.category.lower())
            or fuzzy_score(commodity_name, item.name) > 0.78
        ]
        return filtered[:limit] if filtered else items[:limit]

    async def suggest_trade_route(
        self,
        commodity_name: str,
        from_location: str | None = None,
        budget: float | None = None,
        cargo_scu: float | None = None,
    ) -> RouteSuggestion | None:
        payload = await self.client.get("/commodities_routes")
        records = self._extract_records(payload)
        ranked: list[dict[str, Any]] = []
        for record in records:
            name = str(record.get("commodity_name") or record.get("item_name") or "")
            if fuzzy_score(commodity_name, name) < 0.72:
                continue
            if from_location:
                buy_loc = str(record.get("buy_terminal") or record.get("buy_location") or "")
                if fuzzy_score(from_location, buy_loc) < 0.55:
                    continue
            ranked.append(record)

        if not ranked:
            return None

        def route_score(route: dict[str, Any]) -> float:
            margin = self._safe_float(route.get("profit_margin") or route.get("margin") or 0) or 0
            profit_unit = self._safe_float(route.get("profit_per_scu") or route.get("profit_per_unit") or 0) or 0
            stock = self._safe_float(route.get("scu_buy") or route.get("stock_scu") or 0) or 0
            route_budget = budget or 0
            cargo = cargo_scu or 0
            budget_factor = min(route_budget / 100000.0, 2.0) if route_budget else 1.0
            cargo_factor = min(cargo / 100.0, 2.0) if cargo else 1.0
            return margin + (profit_unit * 2.0) + (stock * 0.01) + budget_factor + cargo_factor

        best = sorted(ranked, key=route_score, reverse=True)[0]
        buy_price = self._safe_float(best.get("price_buy") or best.get("buy_price"))
        sell_price = self._safe_float(best.get("price_sell") or best.get("sell_price"))
        margin = self._safe_float(best.get("profit_per_unit") or best.get("margin"))

        units = cargo_scu or self._safe_float(best.get("scu_buy") or 0) or 0
        if budget and buy_price and buy_price > 0:
            affordable_units = budget / buy_price
            units = min(units or affordable_units, affordable_units)

        estimated_profit = (margin * units) if margin is not None and units else None
        return RouteSuggestion(
            commodity_name=str(best.get("commodity_name") or best.get("item_name") or commodity_name),
            buy_location=str(best.get("buy_terminal") or best.get("buy_location") or "Unknown Buy"),
            sell_location=str(best.get("sell_terminal") or best.get("sell_location") or "Unknown Sell"),
            buy_price=buy_price,
            sell_price=sell_price,
            margin_per_unit=margin,
            estimated_profit=estimated_profit,
            confidence_note="Community data can change with patch updates and local stock changes.",
            raw=best,
        )

    @staticmethod
    def _compose_location_name(record: dict[str, Any]) -> str:
        terminal = str(record.get("terminal_name") or "").strip()
        locality_parts = [
            str(record.get("city_name") or "").strip(),
            str(record.get("space_station_name") or "").strip(),
            str(record.get("outpost_name") or "").strip(),
            str(record.get("moon_name") or "").strip(),
            str(record.get("planet_name") or "").strip(),
            str(record.get("star_system_name") or "").strip(),
        ]
        locality_parts = [part for part in locality_parts if part]
        if terminal and locality_parts:
            return f"{terminal} — {', '.join(locality_parts)}"
        if terminal:
            return terminal
        if locality_parts:
            return ", ".join(locality_parts)
        return "Unknown Location"

    @staticmethod
    def _safe_float(value: Any) -> float | None:
        try:
            if value in (None, ""):
                return None
            return float(value)
        except (TypeError, ValueError):
            return None
