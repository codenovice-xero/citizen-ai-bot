import discord

FOOTER = "Citizen AI • Star Citizen Utility Bot"

def simple_embed(title, description):
    e = discord.Embed(title=title, description=description)
    e.set_footer(text=FOOTER)
    return e

def status_embed(status):
    e = discord.Embed(title="Citizen AI Status")
    e.add_field(name="Bot", value="Online")
    e.add_field(name="UEX", value="Reachable" if status["uex_api"] else "Unreachable")
    e.add_field(name="Wiki", value="Reachable" if status["wiki_api"] else "Unreachable")
    e.set_footer(text=FOOTER)
    return e

def item_embed(name, rows):
    e = discord.Embed(title=f"📦 {name}")
    if not rows:
        e.description = "No item data found."
    else:
        e.description = "\n".join([str(x) for x in rows[:10]])
    e.set_footer(text=FOOTER)
    return e

def loadout_embed(report, query):
    e = discord.Embed(title=f"🛠️ {query}")
    if report is None:
        e.description = "No ship data found."
    else:
        e.description = "Loadout ready."
    e.set_footer(text=FOOTER)
    return e
