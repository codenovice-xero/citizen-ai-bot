from __future__ import annotations

import discord

from .models import LoadoutReport

FOOTER = "Citizen AI • Star Citizen Utility Bot"


def _truncate_lines(lines: list[str], max_len: int = 1000) -> str:
    if not lines:
        return "No data."
    out: list[str] = []
    total = 0
    for line in lines:
        entry = f"• {line}"
        if total + len(entry) + 1 > max_len:
            break
        out.append(entry)
        total += len(entry) + 1
    return "\n".join(out) if out else "No data."


def simple_embed(title: str, description: str) -> discord.Embed:
    embed = discord.Embed(title=title, description=description)
    embed.set_footer(text=FOOTER)
    return embed


def status_embed(status: dict[str, bool]) -> discord.Embed:
    overall_ok = status.get("overall", False)
    embed = discord.Embed(
        title="🟢 Citizen AI Status" if overall_ok else "🟡 Citizen AI Status",
        description=(
            "All connected services answered cleanly."
            if overall_ok
            else "The bot is online, but one or more data providers did not answer cleanly."
        ),
    )
    embed.add_field(name="Bot", value="Online", inline=True)
    embed.add_field(
        name="UEX",
        value="Reachable" if status.get("uex_api") else "Unreachable",
        inline=True,
    )
    embed.add_field(
        name="Wiki",
        value="Reachable" if status.get("wiki_api") else "Unreachable",
        inline=True,
    )
    embed.set_footer(text=FOOTER)
    return embed


def item_embed(item_name: str, rows: list[dict], location: str | None = None, resolved_location: str | None = None) -> discord.Embed:
    title = f"📦 {item_name}"
    if location:
        title += f" • from {location}"

    embed = discord.Embed(title=title)

    if resolved_location:
        embed.description = f"Resolved origin: {resolved_location}"

    if not rows:
        if resolved_location:
            embed.description = f"{embed.description}\n\nNo item data was returned for that query."
        else:
            embed.description = "No item data was returned for that query."
        embed.set_footer(text=FOOTER)
        return embed

    lines: list[str] = []
    for row in rows[:20]:
        terminal = (
            row.get("terminal_name")
            or row.get("terminal")
            or row.get("name_terminal")
            or "Unknown terminal"
        )

        system = row.get("system_name") or row.get("system") or row.get("star_system_name")
        planet = row.get("planet_name") or row.get("planet")
        moon = row.get("moon_name") or row.get("moon")
        city = row.get("city_name") or row.get("city")

        buy = row.get("price_buy") or row.get("buy_price")
        sell = row.get("price_sell") or row.get("sell_price")
        distance_gm = row.get("_distance_gm")

        location_bits = [x for x in (system, planet, moon, city) if x]
        location_suffix = f" ({' • '.join(location_bits)})" if location_bits else ""

        extras: list[str] = []
        if distance_gm is not None:
            extras.append(f"{distance_gm:.2f} GM")
        if buy is not None:
            extras.append(f"buy {buy}")
        if sell is not None:
            extras.append(f"sell {sell}")

        market_suffix = f" — {' | '.join(extras)}" if extras else ""
        lines.append(f"{terminal}{location_suffix}{market_suffix}")

    body = _truncate_lines(lines, 3500)
    if embed.description:
        embed.description = f"{embed.description}\n\n{body}"
    else:
        embed.description = body

    embed.set_footer(text=FOOTER)
    return embed


def loadout_embed(report: LoadoutReport | None, query: str) -> discord.Embed:
    if report is None:
        embed = discord.Embed(title=f"🛠️ {query}")
        embed.description = "No ship data was returned by the Star Citizen Wiki API for that query."
        embed.set_footer(text=FOOTER)
        return embed

    embed = discord.Embed(title=f"🛠️ {report.ship_name}")

    subtitle: list[str] = []
    if getattr(report, "role", None):
        subtitle.append(report.role)
    if getattr(report, "manufacturer", None):
        subtitle.append(report.manufacturer)
    if subtitle:
        embed.description = " • ".join(subtitle)

    weapons = getattr(report, "weapons", []) or []
    systems = getattr(report, "systems", []) or []
    performance = getattr(report, "performance", []) or []
    notes = getattr(report, "notes", []) or []

    embed.add_field(name="Weapons", value=_truncate_lines(weapons), inline=False)
    embed.add_field(name="Systems", value=_truncate_lines(systems), inline=False)
    embed.add_field(name="Performance", value=_truncate_lines(performance), inline=False)
    if notes:
        embed.add_field(name="Notes", value=_truncate_lines(notes), inline=False)

    embed.set_footer(text=FOOTER)
    return embed
