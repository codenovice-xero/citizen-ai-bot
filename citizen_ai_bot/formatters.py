from __future__ import annotations

import discord

from .models import ItemLocation, ItemMatch, RouteSuggestion


def item_embed(query: str, matches: list[ItemMatch], locations: list[ItemLocation]) -> discord.Embed:
    embed = discord.Embed(
        title="Citizen AI • Item Search",
        description=f"Results for **{query}**",
    )
    if matches:
        top = matches[0]
        meta = []
        if top.category:
            meta.append(f"Category: {top.category}")
        if top.company:
            meta.append(f"Maker: {top.company}")
        if top.size:
            meta.append(f"Size: {top.size}")
        if top.item_id is not None:
            meta.append(f"Item ID: {top.item_id}")
        if meta:
            embed.add_field(name="Best match", value=f"**{top.name}**\n" + " | ".join(meta), inline=False)
        else:
            embed.add_field(name="Best match", value=f"**{top.name}**", inline=False)

        if len(matches) > 1:
            alternates = "\n".join(f"• {match.name}" for match in matches[1:5])
            if alternates:
                embed.add_field(name="Other close matches", value=alternates, inline=False)
    else:
        embed.add_field(name="Best match", value="No close match found.", inline=False)

    if locations:
        lines = []
        for loc in locations[:8]:
            parts = [f"**{loc.location_name}**"]
            if loc.buy_price is not None:
                parts.append(f"Buy: {loc.buy_price:,.0f} aUEC")
            if loc.sell_price is not None:
                parts.append(f"Sell: {loc.sell_price:,.0f} aUEC")
            lines.append(" • ".join(parts))
        embed.add_field(name="Likely locations", value="\n".join(lines), inline=False)
    else:
        embed.add_field(
            name="Likely locations",
            value="No shop entries were found from the live source for this item.",
            inline=False,
        )

    embed.set_footer(text="UEX-backed result. Community-maintained data may be incomplete.")
    return embed


def commodity_embed(query: str, matches: list[ItemMatch]) -> discord.Embed:
    embed = discord.Embed(
        title="Citizen AI • Commodity Search",
        description=f"Closest commodity results for **{query}**",
    )
    if not matches:
        embed.add_field(name="Result", value="No close commodity matches found.", inline=False)
        return embed

    lines = []
    for match in matches[:8]:
        details = []
        if match.category:
            details.append(match.category)
        if match.company:
            details.append(match.company)
        details_text = f" — {' | '.join(details)}" if details else ""
        lines.append(f"**{match.name}**{details_text}")
    embed.add_field(name="Matches", value="\n".join(lines), inline=False)
    embed.set_footer(text="Use /route with the commodity name for a route suggestion.")
    return embed


def route_embed(route: RouteSuggestion, budget: float | None = None, cargo_scu: float | None = None) -> discord.Embed:
    embed = discord.Embed(
        title="Citizen AI • Trade Route",
        description=f"Starter route suggestion for **{route.commodity_name}**",
    )
    embed.add_field(name="Buy", value=route.buy_location, inline=True)
    embed.add_field(name="Sell", value=route.sell_location, inline=True)
    embed.add_field(name="Margin / unit", value=f"{route.margin_per_unit:,.2f} aUEC" if route.margin_per_unit is not None else "Unknown", inline=True)

    pricing = []
    if route.buy_price is not None:
        pricing.append(f"Buy: {route.buy_price:,.2f} aUEC")
    if route.sell_price is not None:
        pricing.append(f"Sell: {route.sell_price:,.2f} aUEC")
    if budget is not None:
        pricing.append(f"Budget: {budget:,.0f} aUEC")
    if cargo_scu is not None:
        pricing.append(f"Cargo: {cargo_scu:,.0f} SCU")
    embed.add_field(name="Pricing context", value="\n".join(pricing) if pricing else "No extra pricing details.", inline=False)

    embed.add_field(
        name="Estimated profit",
        value=f"{route.estimated_profit:,.0f} aUEC" if route.estimated_profit is not None else "Not enough data to estimate.",
        inline=False,
    )
    embed.add_field(name="Note", value=route.confidence_note, inline=False)
    return embed


def status_embed(ok: bool) -> discord.Embed:
    embed = discord.Embed(title="Citizen AI • Status")
    embed.add_field(name="Bot", value="Online", inline=True)
    embed.add_field(name="UEX API", value="Reachable" if ok else "Unavailable", inline=True)
    embed.set_footer(text="If UEX is unavailable, slash commands may return partial or empty results.")
    return embed
