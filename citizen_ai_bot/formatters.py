from __future__ import annotations

import discord

from .models import AdvicePlan, ItemLocation, ItemMatch, LoadoutSuggestion, MiningSuggestion, RouteSuggestion
from .utils import fmt_credits, fmt_number

BRAND_NAME = "Citizen AI"
BRAND_FOOTER = "Citizen AI • Star Citizen Utility Bot"


def _base_embed(title: str, description: str | None = None, *, color: discord.Color) -> discord.Embed:
    embed = discord.Embed(title=title, description=description or discord.Embed.Empty, color=color)
    embed.set_footer(text=BRAND_FOOTER)
    return embed


def error_embed(title: str, message: str) -> discord.Embed:
    return _base_embed(f"❌ {title}", message, color=discord.Color.red())


def status_embed(healthy: bool) -> discord.Embed:
    if healthy:
        embed = _base_embed("🟢 Citizen AI Status", "All systems look good and the UEX API responded.", color=discord.Color.green())
        embed.add_field(name="Bot", value="Online", inline=True)
        embed.add_field(name="UEX", value="Reachable", inline=True)
    else:
        embed = _base_embed(
            "🟡 Citizen AI Status",
            "The bot is online, but the UEX health check did not answer cleanly.",
            color=discord.Color.gold(),
        )
        embed.add_field(name="Bot", value="Online", inline=True)
        embed.add_field(name="UEX", value="Unreachable", inline=True)
    return embed


def help_embed() -> discord.Embed:
    embed = _base_embed(
        "🧠 Citizen AI Commands",
        "Use slash commands to search items, scan routes, and get curated Star Citizen guidance.",
        color=discord.Color.blurple(),
    )
    embed.add_field(
        name="Economy",
        value="`/item`\n`/route`\n`/multiroute`\n`/trend`\n`/risk`",
        inline=True,
    )
    embed.add_field(
        name="Guidance",
        value="`/advice`\n`/missions`\n`/op`",
        inline=True,
    )
    embed.add_field(
        name="Ships & Roles",
        value="`/loadout`\n`/mining`\n`/status`",
        inline=True,
    )
    embed.add_field(
        name="Examples",
        value=(
            "`/item name: Omnisky`\n"
            "`/route commodity: Gold`\n"
            "`/multiroute commodity: Laranite budget: 250000 scu: 96`\n"
            "`/advice money: 200000 ship: Cutlass Black`"
        ),
        inline=False,
    )
    return embed


def format_item_result(matches: list[ItemMatch], locations: list[ItemLocation]) -> discord.Embed:
    if not matches:
        return _base_embed(
            "🔎 Item Search",
            "No item matches found. Try a broader name or a shorter keyword.",
            color=discord.Color.red(),
        )

    best = matches[0]
    title = f"🔎 {best.name}"
    subtitle_bits: list[str] = []
    if best.category:
        subtitle_bits.append(best.category)
    if best.company:
        subtitle_bits.append(best.company)
    if best.size:
        subtitle_bits.append(f"Size {best.size}")

    embed = _base_embed(title, " • ".join(subtitle_bits) if subtitle_bits else None, color=discord.Color.blue())

    if best.uuid is not None:
        embed.add_field(name="Item ID", value=str(best.uuid), inline=True)
    embed.add_field(name="Match Quality", value="Best available result", inline=True)

    alt = [match.name for match in matches[1:4] if match.name != best.name]
    if alt:
        embed.add_field(name="Also matched", value="\n".join(f"• {name}" for name in alt), inline=False)

    if not locations:
        embed.add_field(name="Locations", value="No location rows came back for this item right now.", inline=False)
        return embed

    lines: list[str] = []
    for idx, location in enumerate(locations[:6], start=1):
        price_bits: list[str] = []
        if location.buy_price is not None:
            price_bits.append(f"buy **{fmt_credits(location.buy_price)}**")
        if location.sell_price is not None:
            price_bits.append(f"sell **{fmt_credits(location.sell_price)}**")
        if location.scu is not None:
            price_bits.append(f"stock {fmt_number(location.scu, 0)}")
        suffix = f" — {' • '.join(price_bits)}" if price_bits else ""
        lines.append(f"`{idx}.` {location.location_name}{suffix}")

    embed.add_field(name="Locations", value="\n".join(lines), inline=False)
    return embed


def format_route(route: RouteSuggestion) -> discord.Embed:
    color = {
        "Low": discord.Color.green(),
        "Moderate": discord.Color.gold(),
        "High": discord.Color.orange(),
        "Extreme": discord.Color.red(),
    }.get(route.risk_label or "", discord.Color.green())

    embed = _base_embed(f"🚚 Best {route.commodity_name} Route", None, color=color)
    embed.add_field(name="Buy", value=f"{route.buy_location}\n**{fmt_credits(route.buy_price)}**", inline=True)
    embed.add_field(name="Sell", value=f"{route.sell_location}\n**{fmt_credits(route.sell_price)}**", inline=True)
    embed.add_field(name="Margin / Unit", value=fmt_credits(route.margin_per_unit), inline=True)

    embed.add_field(name="Estimated Profit", value=fmt_credits(route.estimated_profit), inline=True)
    embed.add_field(name="Risk", value=route.risk_label or "n/a", inline=True)
    embed.add_field(name="Commodity", value=route.commodity_name, inline=True)

    if route.confidence_note:
        embed.add_field(name="Note", value=route.confidence_note, inline=False)
    return embed


def format_route_list(routes: list[RouteSuggestion]) -> discord.Embed:
    if not routes:
        return _base_embed(
            "📈 Route Options",
            "No routes found for that query. Try a different commodity or a looser origin filter.",
            color=discord.Color.red(),
        )

    embed = _base_embed(
        f"📈 Top {len(routes)} Route Options",
        "Ranked by estimated profit, then margin per unit.",
        color=discord.Color.teal(),
    )

    for idx, route in enumerate(routes[:5], start=1):
        value = (
            f"**Buy:** {route.buy_location} @ {fmt_credits(route.buy_price)}\n"
            f"**Sell:** {route.sell_location} @ {fmt_credits(route.sell_price)}\n"
            f"**Margin:** {fmt_credits(route.margin_per_unit)} • **Est:** {fmt_credits(route.estimated_profit)} • **Risk:** {route.risk_label or 'n/a'}"
        )
        embed.add_field(name=f"#{idx} • {route.commodity_name}", value=value, inline=False)
    return embed


def format_advice(plan: AdvicePlan) -> discord.Embed:
    embed = _base_embed(f"🧠 {plan.title}", plan.summary, color=discord.Color.purple())
    bullets = "\n".join(f"• {bullet}" for bullet in plan.bullets[:10]) or "No guidance available."
    embed.add_field(name="Plan", value=bullets, inline=False)
    return embed


def format_loadout(loadout: LoadoutSuggestion | None, requested_ship: str) -> discord.Embed:
    if not loadout:
        return _base_embed(
            f"🛠️ {requested_ship}",
            "No curated loadout entry yet. Add it to `static_data.py` to expand coverage.",
            color=discord.Color.red(),
        )

    embed = _base_embed(f"🛠️ {loadout.ship_name} Loadout", f"Role: **{loadout.role}**", color=discord.Color.gold())
    embed.add_field(name="Weapons", value="\n".join(f"• {item}" for item in loadout.weapons) or "n/a", inline=False)
    embed.add_field(name="Shields", value="\n".join(f"• {item}" for item in loadout.shields) or "n/a", inline=True)
    embed.add_field(
        name="Power / Coolers",
        value="\n".join(f"• {item}" for item in loadout.power + loadout.coolers) or "n/a",
        inline=True,
    )
    embed.add_field(name="Notes", value="\n".join(f"• {item}" for item in loadout.notes) or "n/a", inline=False)
    return embed


def format_mining(plan: MiningSuggestion | None, requested_ship: str) -> discord.Embed:
    if not plan:
        return _base_embed(
            f"⛏️ {requested_ship}",
            "No curated mining entry yet. Add it to `static_data.py` to expand coverage.",
            color=discord.Color.red(),
        )

    embed = _base_embed(f"⛏️ {plan.ship_name} Mining Plan", None, color=discord.Color.orange())
    embed.add_field(name="Modules", value="\n".join(f"• {item}" for item in plan.modules) or "n/a", inline=False)
    embed.add_field(name="Focus", value="\n".join(f"• {item}" for item in plan.focus) or "n/a", inline=False)
    embed.add_field(name="Notes", value="\n".join(f"• {item}" for item in plan.notes) or "n/a", inline=False)
    return embed


def format_risk(label: str, notes: list[str]) -> discord.Embed:
    color = {
        "Low": discord.Color.green(),
        "Moderate": discord.Color.gold(),
        "High": discord.Color.orange(),
        "Extreme": discord.Color.red(),
    }.get(label, discord.Color.light_grey())
    embed = _base_embed(f"⚠️ Route Risk: {label}", None, color=color)
    embed.add_field(name="Assessment", value="\n".join(f"• {note}" for note in notes) if notes else "No extra notes.", inline=False)
    return embed


def format_trend(snapshot: dict) -> discord.Embed:
    route = snapshot["top_route"]
    embed = _base_embed(f"📊 {snapshot['commodity']} Snapshot", snapshot["trend_note"], color=discord.Color.fuchsia())
    embed.add_field(name="Best Margin Seen", value=fmt_credits(snapshot["best_margin"]), inline=True)
    embed.add_field(name="Average Margin", value=fmt_credits(snapshot["avg_margin"]), inline=True)
    embed.add_field(name="Top Route Risk", value=route.risk_label or "n/a", inline=True)
    embed.add_field(name="Top Buy", value=f"{route.buy_location}\n**{fmt_credits(route.buy_price)}**", inline=True)
    embed.add_field(name="Top Sell", value=f"{route.sell_location}\n**{fmt_credits(route.sell_price)}**", inline=True)
    embed.add_field(name="Estimated Profit", value=fmt_credits(route.estimated_profit), inline=True)
    return embed
