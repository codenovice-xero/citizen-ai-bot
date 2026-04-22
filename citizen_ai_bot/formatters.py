from __future__ import annotations
import discord

FOOTER = "Citizen AI • Star Citizen Utility Bot"


def simple_embed(title: str, description: str):
    e = discord.Embed(title=title, description=description)
    e.set_footer(text=FOOTER)
    return e


def status_embed(status: dict):
    ok = status.get("overall", False)

    e = discord.Embed(
        title="🟢 Citizen AI Status" if ok else "🟡 Citizen AI Status",
        description="All systems operational." if ok else "One or more providers unreachable."
    )

    e.add_field(name="Bot", value="Online", inline=True)
    e.add_field(name="UEX", value="Reachable" if status.get("uex_api") else "Unreachable", inline=True)
    e.add_field(name="Wiki", value="Reachable" if status.get("wiki_api") else "Unreachable", inline=True)

    e.set_footer(text=FOOTER)
    return e


def item_embed(item_name: str, rows: list):
    e = discord.Embed(title=f"📦 {item_name}")

    if not rows:
        e.description = "No item data was returned for that query."
        e.set_footer(text=FOOTER)
        return e

    lines = []

    for row in rows[:15]:
        terminal = row.get("terminal_name") or row.get("terminal") or "Unknown terminal"
        buy = row.get("price_buy") or row.get("buy_price")
        sell = row.get("price_sell") or row.get("sell_price")

        text = terminal

        if buy is not None:
            text += f" | Buy {buy}"

        if sell is not None:
            text += f" | Sell {sell}"

        lines.append(text)

    e.description = "\n".join(lines[:15])
    e.set_footer(text=FOOTER)
    return e


def loadout_embed(report, query: str):
    e = discord.Embed(title=f"🛠️ {query}")

    if report is None:
        e.description = "No ship data was returned by the Star Citizen Wiki API for that query."
        e.set_footer(text=FOOTER)
        return e

    subtitle = []

    if getattr(report, "role", None):
        subtitle.append(report.role)

    if getattr(report, "manufacturer", None):
        subtitle.append(report.manufacturer)

    if subtitle:
        e.description = " • ".join(subtitle)

    e.add_field(name="Weapons", value="\n".join(report.weapons[:10]) or "None", inline=False)
    e.add_field(name="Systems", value="\n".join(report.systems[:10]) or "None", inline=False)
    e.add_field(name="Performance", value="\n".join(report.performance[:10]) or "None", inline=False)

    if getattr(report, "notes", None):
        e.add_field(name="Notes", value="\n".join(report.notes[:10]), inline=False)

    e.set_footer(text=FOOTER)
    return e
