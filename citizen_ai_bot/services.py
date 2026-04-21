from __future__ import annotations

import logging
from typing import Any

from .config import settings
from .models import AdvicePlan, ItemLocation, ItemMatch, MiningSuggestion, RouteSuggestion
from .uex_client import UEXClient
from .utils import fuzzy_score, normalize_text
from .wiki_client import WikiClient

log = logging.getLogger(__name__)


class StarCitizenService:
    """
    Full service layer preserving the current cog contract.
    """

    def __init__(self, client: Any | None = None) -> None:
        self.client = client or UEXClient(api_token=settings.uex_api_token)
        self.wiki = WikiClient()

    async def close(self) -> None:
        try:
            if self.client and hasattr(self.client, "close"):
                maybe = self.client.close()
                if hasattr(maybe, "__await__"):
                    await maybe
        except Exception:
            log.exception("Failed closing primary client")

        try:
            await self.wiki.close()
        except Exception:
            log.exception("Failed closing wiki client")

    async def health_status(self) -> dict[str, bool]:
        uex_ok = False
        wiki_ok = False
        if self.client and hasattr(self.client, "ping"):
            try:
                maybe = self.client.ping()
                uex_ok = await maybe if hasattr(maybe, "__await__") else bool(maybe)
            except Exception:
                uex_ok = False
        try:
            wiki_ok = await self.wiki.ping()
        except Exception:
            wiki_ok = False
        return {"uex": uex_ok, "wiki": wiki_ok}

    async def get_item_locations(self, name: str) -> tuple[list[ItemMatch], list[ItemLocation]]:
        matches = await self.wiki.search_items_best(name, limit=5)
        if not matches:
            return [], []

        best = matches[0]
        # Enrich the best match with UEX metadata where available.
        if best.uuid:
            try:
                uex_rows = await self.client.get_item_by_uuid(best.uuid)
            except Exception:
                uex_rows = []
            if uex_rows:
                row = uex_rows[0]
                best.category = best.category or row.get("category") or row.get("section")
                best.company = best.company or row.get("company_name")
                best.size = best.size or (str(row.get("size")) if row.get("size") is not None else None)

        locations: list[ItemLocation] = []
        if best.uuid:
            try:
                price_rows = await self.client.get_item_prices_by_uuid(best.uuid)
            except Exception:
                price_rows = []
            for row in price_rows[:10]:
                location_bits = [
                    row.get("terminal_name"),
                    row.get("city_name"),
                    row.get("space_station_name"),
                    row.get("outpost_name"),
                    row.get("moon_name"),
                    row.get("planet_name"),
                ]
                loc_name = " / ".join(dict.fromkeys(str(bit) for bit in location_bits if bit))
                locations.append(
                    ItemLocation(
                        location_name=loc_name or "Unknown terminal",
                        buy_price=_to_float(row.get("price_buy")),
                        sell_price=_to_float(row.get("price_sell")),
                        scu=_to_float(row.get("scu") or row.get("stock") or row.get("inventory")),
                        terminal_code=row.get("terminal_code"),
                        terminal_name=row.get("terminal_name"),
                    )
                )
        return matches, locations

    async def _commodity_market_rows(self, commodity_name: str) -> list[dict[str, Any]]:
        rows = await self.client.get_commodity_prices(commodity_name)
        if rows:
            return rows
        # Fallback on best commodity_code/name from returned rows is not available without a directory.
        return []

    def _build_location_name(self, row: dict[str, Any]) -> str:
        bits = [
            row.get("terminal_name"),
            row.get("city_name"),
            row.get("space_station_name"),
            row.get("outpost_name"),
            row.get("moon_name"),
            row.get("planet_name"),
            row.get("star_system_name"),
        ]
        return " / ".join(dict.fromkeys(str(bit) for bit in bits if bit)) or "Unknown location"

    def _risk_for_locations(self, buy_location: str, sell_location: str, legal_only: bool = False) -> tuple[str, list[str]]:
        label = "Low"
        notes: list[str] = []
        joined = f"{buy_location} {sell_location}".lower()
        if any(word in joined for word in ("pyro", "jumptown", "contested", "outpost")):
            label = "High"
            notes.append("One or both locations look contested or remote.")
        if any(word in joined for word in ("city", "station", "new babbage", "lorville", "area18", "orison")) and label == "Low":
            notes.append("Major hubs usually have better access and lower route friction.")
        if legal_only:
            notes.append("Filtered for legal-only intent.")
        if not notes:
            notes.append("Risk is inferred from location type only, not live player activity.")
        return label, notes

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

    async def list_trade_routes(
        self,
        commodity_name: str,
        from_location: str | None = None,
        budget: float | None = None,
        cargo_scu: float | None = None,
        legal_only: bool = False,
        limit: int = 5,
    ) -> list[RouteSuggestion]:
        rows = await self._commodity_market_rows(commodity_name)
        if not rows:
            return []

        floc = normalize_text(from_location)
        buys: list[dict[str, Any]] = []
        sells: list[dict[str, Any]] = []

        for row in rows:
            location_name = self._build_location_name(row)
            if floc and floc not in normalize_text(location_name):
                pass  # only used to boost buy candidates below
            buy_price = _to_float(row.get("price_buy"))
            sell_price = _to_float(row.get("price_sell"))
            if buy_price and buy_price > 0:
                buy_copy = dict(row)
                buy_copy["_location_name"] = location_name
                buys.append(buy_copy)
            if sell_price and sell_price > 0:
                sell_copy = dict(row)
                sell_copy["_location_name"] = location_name
                sells.append(sell_copy)

        if not buys or not sells:
            return []

        if floc:
            matching_buys = [row for row in buys if floc in normalize_text(row["_location_name"])]
            if matching_buys:
                buys = matching_buys

        suggestions: list[RouteSuggestion] = []
        cargo = cargo_scu or 100.0

        for buy in sorted(buys, key=lambda r: _to_float(r.get("price_buy")) or 10**9)[:8]:
            for sell in sorted(sells, key=lambda r: _to_float(r.get("price_sell")) or 0, reverse=True)[:12]:
                if buy["_location_name"] == sell["_location_name"]:
                    continue
                buy_price = _to_float(buy.get("price_buy"))
                sell_price = _to_float(sell.get("price_sell"))
                if buy_price is None or sell_price is None or sell_price <= buy_price:
                    continue
                margin = sell_price - buy_price
                effective_scu = cargo
                if budget and buy_price > 0:
                    effective_scu = min(effective_scu, budget / buy_price)
                if effective_scu <= 0:
                    continue
                risk_label, notes = self._risk_for_locations(buy["_location_name"], sell["_location_name"], legal_only=legal_only)
                suggestions.append(
                    RouteSuggestion(
                        commodity_name=str(_first_non_empty(buy.get("commodity_name"), sell.get("commodity_name"), commodity_name)),
                        buy_location=buy["_location_name"],
                        sell_location=sell["_location_name"],
                        buy_price=buy_price,
                        sell_price=sell_price,
                        margin_per_unit=margin,
                        estimated_profit=margin * effective_scu,
                        risk_label=risk_label,
                        confidence_note=notes[0] if notes else None,
                    )
                )

        suggestions.sort(key=lambda r: (r.estimated_profit, r.margin_per_unit), reverse=True)
        return suggestions[:limit]

    def advice_for_player(
        self,
        money: float | None = None,
        ship: str | None = None,
        risk_tolerance: str | None = None,
    ) -> AdvicePlan:
        profile = normalize_text(risk_tolerance) or "medium"
        title = "Citizen AI Activity Plan"
        bullets: list[str] = []

        if profile == "low":
            summary = "Focus on safer progression and lower-volatility earnings."
            bullets.extend([
                "Run legal cargo and delivery loops between major hubs.",
                "Prefer bounty starter chains only after upgrading shields and weapons.",
                "Avoid Pyro, contested zones, and player-owned terminals for now.",
            ])
        elif profile == "high":
            summary = "Lean into higher-risk, higher-variance opportunities."
            bullets.extend([
                "Prioritize PvE bounty chains, salvage competition, and rare-loot runs.",
                "Carry only what you can afford to lose.",
                "Keep a fast claim-ready backup ship available.",
            ])
        else:
            summary = "Balance profit, survivability, and steady ship progression."
            bullets.extend([
                "Mix commodity hauling with mission chains to keep cash flow steady.",
                "Upgrade your main ship before overextending into risky zones.",
                "Use route and risk checks before committing cargo capital.",
            ])

        if money is not None:
            bullets.append(f"Current budget reference: about {money:,.0f} aUEC.")
        if ship:
            bullets.append(f"Primary ship on file: {ship}.")
        bullets.append("Use /route and /trend to validate the next money-making loop.")
        return AdvicePlan(title=title, summary=summary, bullets=bullets)

    async def suggest_loadout(self, ship_name: str):
        return await self.wiki.build_loadout_report(ship_name)

    def suggest_mining(self, ship_name: str) -> MiningSuggestion | None:
        name = normalize_text(ship_name)
        if "prospector" in name:
            return MiningSuggestion(
                ship_name="Prospector",
                modules=["Helix laser for stronger break power", "Mix stability and resistance modules", "Carry surge tools only when fracture support is needed"],
                focus=["Quantanium only if you can return fast", "Headanite and Bexalite are safer filler targets"],
                notes=["Solo-friendly option", "Watch cargo timer discipline on volatile ore"],
            )
        if "mole" in name:
            return MiningSuggestion(
                ship_name="Mole",
                modules=["Dedicated fracture head on the main laser", "Support lasers tuned for stability and inert material control", "Coordinate module roles by seat"],
                focus=["Best with two or three players", "Split roles between scanner, pilot, and fracture support"],
                notes=["Excellent yield when crewed", "Plan refinery follow-up before leaving the belt"],
            )
        if "golem" in name:
            return MiningSuggestion(
                ship_name="Golem",
                modules=["Run stability-heavy modules first", "Tune for surface mining consistency over peak fracture power"],
                focus=["Surface rocks and efficient solo cycles"],
                notes=["Compact and practical for smaller operations"],
            )
        return None

    def mission_plan(self, mission_type: str) -> AdvicePlan:
        q = normalize_text(mission_type)
        bullets = []
        title = "Mission Path Guidance"
        if "bounty" in q:
            bullets = [
                "Start with legal bounty certifications and scale threat slowly.",
                "Upgrade shields first, then weapons, then coolers if heat becomes the limiter.",
                "Always restock missiles before long bounty chains.",
            ]
            summary = "Combat progression path built around repeatable legal bounty income."
        elif "bunker" in q or "merc" in q:
            bullets = [
                "Bring medpens, multitool tractor support, and spare storage.",
                "Use local inventory staging before chaining bunker runs.",
                "Loot selectively so turnaround stays fast.",
            ]
            summary = "Ground mission setup focused on steady repetition and survivability."
        else:
            bullets = [
                "Plan missions around your ship’s current strengths.",
                "Avoid chaining long-distance contracts without fuel and resupply checks.",
                "Use group content when the payout justifies the coordination overhead.",
            ]
            summary = "General mission planning with an emphasis on efficient completion."
        return AdvicePlan(title=title, summary=summary, bullets=bullets)

    def estimate_route_risk(self, buy_location: str, sell_location: str, legal_only: bool = False) -> tuple[str, list[str]]:
        return self._risk_for_locations(buy_location, sell_location, legal_only=legal_only)

    async def price_snapshot(self, commodity: str) -> dict[str, Any] | None:
        routes = await self.list_trade_routes(commodity_name=commodity, limit=8)
        if not routes:
            return None
        margins = [route.margin_per_unit for route in routes]
        best = routes[0]
        return {
            "commodity": best.commodity_name,
            "top_route": best,
            "best_margin": max(margins),
            "avg_margin": sum(margins) / len(margins),
            "snapshot_note": "Current UEX market snapshot based on live buy/sell rows. This is not long-range historical trend analysis.",
        }

    def plan_operation(self, event: str) -> AdvicePlan:
        return AdvicePlan(
            title="Operation Checklist",
            summary=f"Quick org plan for: {event}",
            bullets=[
                "Define objective, staging point, and extraction point.",
                "Assign at least one logistics pilot and one overwatch element.",
                "Set medbed, gear, and resupply expectations before departure.",
                "Clarify loot rules and exfil trigger conditions.",
                "Have a fallback regroup location if the first site goes hot.",
            ],
        )


def _first_non_empty(*values: Any) -> Any | None:
    for value in values:
        if value is None:
            continue
        if isinstance(value, str):
            stripped = value.strip()
            if stripped:
                return stripped
            continue
        if isinstance(value, (int, float)):
            return value
        if isinstance(value, dict) and value:
            return value
        if isinstance(value, list) and value:
            return value
    return None


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = value.strip().replace(",", "")
        if not cleaned:
            return None
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None
