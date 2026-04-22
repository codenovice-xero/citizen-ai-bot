import discord

FOOTER = "Citizen AI • Star Citizen Utility Bot"


def status_embed(status):
    ok = status["overall"]

    embed = discord.Embed(
        title="🟢 Citizen AI Status" if ok else "🟡 Citizen AI Status",
        description="All systems operational." if ok else "One or more providers unreachable."
    )

    embed.add_field(name="Bot", value="Online")
    embed.add_field(name="UEX", value="Reachable" if status["uex_api"] else "Unreachable")
    embed.add_field(name="Wiki", value="Reachable" if status["wiki_api"] else "Unreachable")
    embed.set_footer(text=FOOTER)
    return embed


def loadout_embed(report, query):
    if report is None:
        embed = discord.Embed(title=f"🛠️ {query}")
        embed.description = "No ship data returned."
        embed.set_footer(text=FOOTER)
        return embed

    embed = discord.Embed(title=f"🛠️ {report.ship_name}")
    embed.description = f"{report.role} • {report.manufacturer}"

    embed.add_field(name="Weapons", value="\n".join(f"• {x}" for x in report.weapons), inline=False)
    embed.add_field(name="Systems", value="\n".join(f"• {x}" for x in report.systems), inline=False)
    embed.add_field(name="Performance", value="\n".join(f"• {x}" for x in report.performance), inline=False)
    embed.add_field(name="Notes", value="\n".join(f"• {x}" for x in report.notes), inline=False)

    embed.set_footer(text=FOOTER)
    return embed
