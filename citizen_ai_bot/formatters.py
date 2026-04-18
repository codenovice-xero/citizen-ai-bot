from __future__ import annotations

from .models import AdvicePlan, ItemLocation, ItemMatch, LoadoutSuggestion, MiningSuggestion, RouteSuggestion
from .utils import fmt_credits, fmt_number


def format_item_result(matches: list[ItemMatch], locations: list[ItemLocation]) -> str:
    if not matches:
        return "No item matches found. Try a broader item name."

    lines = [f"**Best item match:** {matches[0].name}"]
    if matches[0].category:
        lines.append(f"Category: {matches[0].category}")
    if matches[0].company:
        lines.append(f"Company: {matches[0].company}")

    alt = [match.name for match in matches[1:4]]
    if alt:
        lines.append(f"Other likely matches: {', '.join(alt)}")

    if not locations:
        lines.append("No location rows came back for this item right now.")
        return "\n".join(lines)

    lines.append("\n**Locations**")
    for location in locations[:8]:
        bits = [f"• {location.location_name}"]
        if location.buy_price is not None:
            bits.append(f"buy {fmt_credits(location.buy_price)}")
        if location.sell_price is not None:
            bits.append(f"sell {fmt_credits(location.sell_price)}")
        lines.append(" | ".join(bits))
    return "\n".join(lines)


def format_route(route: RouteSuggestion) -> str:
    lines = [
        f"**{route.commodity_name}**",
        f"Buy: {route.buy_location} @ {fmt_credits(route.buy_price)}",
        f"Sell: {route.sell_location} @ {fmt_credits(route.sell_price)}",
        f"Margin/unit: {fmt_credits(route.margin_per_unit)}",
    ]
    if route.estimated_profit is not None:
        lines.append(f"Estimated profit: {fmt_credits(route.estimated_profit)}")
    if route.risk_label:
        lines.append(f"Risk: {route.risk_label}")
    if route.confidence_note:
        lines.append(route.confidence_note)
    return "\n".join(lines)


def format_route_list(routes: list[RouteSuggestion]) -> str:
    if not routes:
        return "No routes found for that query. Try a different commodity or a looser origin filter."
    lines = ["**Top route options**"]
    for idx, route in enumerate(routes, start=1):
        lines.append(
            f"{idx}. {route.commodity_name}: {route.buy_location} -> {route.sell_location} | "
            f"margin {fmt_credits(route.margin_per_unit)} | est {fmt_credits(route.estimated_profit)} | risk {route.risk_label or 'n/a'}"
        )
    return "\n".join(lines)


def format_advice(plan: AdvicePlan) -> str:
    lines = [f"**{plan.title}**", plan.summary]
    lines.extend(f"• {bullet}" for bullet in plan.bullets)
    return "\n".join(lines)


def format_loadout(loadout: LoadoutSuggestion | None, requested_ship: str) -> str:
    if not loadout:
        return f"No curated loadout entry yet for {requested_ship}. Add it to static_data.py to expand coverage."
    lines = [f"**{loadout.ship_name}**", f"Role: {loadout.role}", "**Weapons**"]
    lines.extend(f"• {item}" for item in loadout.weapons)
    lines.append("**Shields**")
    lines.extend(f"• {item}" for item in loadout.shields)
    lines.append("**Power / Coolers**")
    lines.extend(f"• {item}" for item in loadout.power + loadout.coolers)
    lines.append("**Notes**")
    lines.extend(f"• {item}" for item in loadout.notes)
    return "\n".join(lines)


def format_mining(plan: MiningSuggestion | None, requested_ship: str) -> str:
    if not plan:
        return f"No curated mining entry yet for {requested_ship}. Add it to static_data.py to expand coverage."
    lines = [f"**{plan.ship_name} mining plan**", "**Modules**"]
    lines.extend(f"• {item}" for item in plan.modules)
    lines.append("**Focus**")
    lines.extend(f"• {item}" for item in plan.focus)
    lines.append("**Notes**")
    lines.extend(f"• {item}" for item in plan.notes)
    return "\n".join(lines)
