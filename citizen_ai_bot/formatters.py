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
    ok = status.get("overall", False)

    embed = discord.Embed(
        title="🟢 Citizen AI Status" if ok else "🟡 Citizen AI Status",
        description="All systems operational." if ok else "The bot is online, but one or more data providers did not answer cleanly.",
    )
    embed.add_field(name="Bot", value="Online", inline=True)
    embed.add_field(name="UEX", value="Reachable" if status.get("uex_api") else "Unreachable", inline=True)
    embed.add_field(name="Wiki", value="Reachable" if status.get("wiki_api") else "Unreachable", inline=True)
    embed.set_footer(text=FOOTER)
    return embed


def item_embed(item_name: str, rows: list[dict]) -> discord.Embed:
    embed = discord.Embed(title=f"📦 {item_name}")

    if not rows:
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
        buy = row.get("price_buy") or row.get("buy_price")
        sell = row.get("price_sell") or row.get("sell_price")

        extras: list[str] = []
        if buy is not None:
            extras.append(f"buy {buy}")
        if sell is not None:
            extras.append(f"sell {sell}")

        suffix = f" — {' / '.join(extras)}" if extras else ""
        lines.append(f"{terminal}{suffix}")

    embed.description = _truncate_lines(lines, 3500)
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
    if report.role:
        subtitle.append(report.role)
    if report.manufacturer:
        subtitle.append(report.manufacturer)
    if subtitle:
        embed.description = " • ".join(subtitle)

    embed.add_field(name="Weapons", value=_truncate_lines(report.weapons), inline=False)
    embed.add_field(name="Systems", value=_truncate_lines(report.systems), inline=False)
    embed.add_field(name="Performance", value=_truncate_lines(report.performance), inline=False)
    if report.notes:
        embed.add_field(name="Notes", value=_truncate_lines(report.notes), inline=False)

    embed.set_footer(text=FOOTER)
    return embed
