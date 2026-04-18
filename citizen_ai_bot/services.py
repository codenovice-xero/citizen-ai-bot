from __future__ import annotations

import time
from typing import Any

from .models import ItemLocation, ItemMatch, RouteSuggestion
from .uex_client import UEXClient
from .utils import fuzzy_score


class StarCitizenService:
    def __init__(self, client: UEXClient) -> None:
        self.client = client
        self._items_prices_all_cache: list[dict[str, Any]] = []
        self._items_prices_all_cache_ts: float = 0.0
        self._items_prices_all_cache_ttl: int = 60 * 30  # 30 minutes

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

            # Looser filter so partial names like "Omnisky" or "FS-9" work better
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

        results: list[ItemMatch] = []
        for record in ranked[:limit]:
            results.append(
                ItemMatch(
                    name=str(record.get("item_name", "Unknown Item")),
                    uuid=record.get("id_item"),
                    category=str(record.get("category", "")) or None,
                    company=str(record.get("company_name", "")) or None,
                    size=str(record.get("size", "")) or None,
                    raw=record.get("raw", record),
                )
            )
        return results

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
            record_item_name = str(record.get("item_name", "") or best_match.name)
            location_name = self._location_label(record)

            locations.append(
                ItemLocation(
                    item_name=record_item_name,
                    location_name=location_name,
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

        locations = sorted(locations, key=location_sort_key)
        return item_matches, locations[:limit]

    async def search_commodity(self, commodity_name: str, limit: int = 10) -> list[ItemMatch]:
        payload = await self.client.get("/commodities_prices", params={"commodity_name": commodity_name})
        records = self._extract_records(payload)

        seen: set[str] = set()
        ranked = sorted(
            records,
            key=lambda r: fuzzy_score(commodity_name, str(r.get("commodity_name", ""))),
            reverse=True,
        )

        matches: list[ItemMatch] = []
        for record in ranked:
            name = str(record.get("commodity_name", "") or "Unknown Commodity")
            slug = str(record.get("commodity_slug", "") or "")
            dedupe_key = slug or name.lower()
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            matches.append(
                ItemMatch(
                    name=name,
                    uuid=None,
                    category="Commodity",
                    company=None,
                    size=None,
                    raw=record,
                )
            )
            if len(matches) >= limit:
                break
        return matches

    async def suggest_trade_route(
        self,
        commodity_name: str,
        from_location: str | None = None,
        budget: float | None = None,
        cargo_scu: float | None = None,
    ) -> RouteSuggestion | None:
        payload = await self.client.get("/commodities_prices", params={"commodity_name": commodity_name})
        records = self._extract_records(payload)
        if not records:
            return None

        relevant: list[dict[str, Any]] = []
        for record in records:
            name = str(record.get("commodity_name") or "")
            if fuzzy_score(commodity_name, name) < 0.72:
                continue
            if from_location:
                candidate = " ".join(
                    str(record.get(key) or "")
                    for key in (
                        "terminal_name",
                        "city_name",
                        "outpost_name",
                        "space_station_name",
                        "planet_name",
                        "moon_name",
                    )
                )
                if fuzzy_score(from_location, candidate) < 0.55:
                    continue
            relevant.append(record)

        if not relevant:
            return None

        buy_candidates = [r for r in relevant if self._safe_float(r.get("price_buy")) not in (None, 0)]
        sell_candidates = [r for r in relevant if self._safe_float(r.get("price_sell")) not in (None, 0)]
        if not buy_candidates or not sell_candidates:
            return None

        def buy_score(row: dict[str, Any]) -> tuple[float, float, float]:
            price = self._safe_float(row.get("price_buy")) or float("inf")
            stock = self._safe_float(row.get("scu_buy") or row.get("scu_buy_avg") or 0) or 0.0
            quality = self._safe_float(row.get("quality") or row.get("quality_avg") or 0) or 0.0
            return (price, -stock, -quality)

        def sell_score(row: dict[str, Any]) -> tuple[float, float, float]:
            price = self._safe_float(row.get("price_sell")) or 0.0
            demand = self._safe_float(row.get("scu_sell") or row.get("scu_sell_avg") or 0) or 0.0
            quality = self._safe_float(row.get("quality") or row.get("quality_avg") or 0) or 0.0
            return (-price, -demand, -quality)

        buy_row = sorted(buy_candidates, key=buy_score)[0]
        sell_row = sorted(sell_candidates, key=sell_score)[0]

        if self._location_label(buy_row) == self._location_label(sell_row):
            alternatives = sorted(sell_candidates, key=sell_score)
            sell_row = next(
                (row for row in alternatives if self._location_label(row) != self._location_label(buy_row)),
                sell_row,
            )

        buy_price = self._safe_float(buy_row.get("price_buy"))
        sell_price = self._safe_float(sell_row.get("price_sell"))
        if buy_price is None or sell_price is None or sell_price <= buy_price:
            return None

        margin = sell_price - buy_price

        units = cargo_scu or self._safe_float(buy_row.get("scu_buy") or buy_row.get("scu_buy_avg") or 0) or 0
        if budget and buy_price > 0:
            affordable_units = budget / buy_price
            units = min(units or affordable_units, affordable_units)

        estimated_profit = margin * units if units else None
        return RouteSuggestion(
            commodity_name=str(buy_row.get("commodity_name") or commodity_name),
            buy_location=self._location_label(buy_row),
            sell_location=self._location_label(sell_row),
            buy_price=buy_price,
            sell_price=sell_price,
            margin_per_unit=margin,
            estimated_profit=estimated_profit,
            confidence_note="Calculated from live UEX commodity prices. Data is community-maintained and can shift quickly.",
            raw={"buy": buy_row, "sell": sell_row},
        )

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
