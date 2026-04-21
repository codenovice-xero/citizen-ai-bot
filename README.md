# Citizen AI Bot

Discord utility bot for Star Citizen with slash commands for item lookups, trade routes, risk checks, mission guidance, mining suggestions, and ship loadout recommendations enriched with Star Citizen Wiki data.

## Included fixes

- Clean deployable repo structure instead of a partial patch pack.
- Proper `requirements.txt` formatting.
- `.env.example` for first-time setup.
- `Procfile` for Railway deployment.
- `/status` now checks both UEX and the Star Citizen Wiki API.
- `/advice` now actually uses `risk_tolerance`.
- `/trend` text now clearly describes the result as a live market snapshot.
- Removed noisy debug prints from the loadout enrichment path.

## Requirements

- Python 3.11+
- A Discord bot token

## Local setup

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env       # Windows: copy .env.example .env
```

Fill in `DISCORD_TOKEN` in `.env`, then run:

```bash
python -m citizen_ai_bot
```

## Railway deployment

1. Create a new Railway project from this repo.
2. Add your environment variables from `.env.example`.
3. Railway can use the included `Procfile` automatically.
4. Deploy.

Recommended Railway variables:

- `DISCORD_TOKEN`
- `DISCORD_GUILD_ID` (optional, but useful while testing slash command sync)
- `UEX_API_TOKEN` (optional unless your UEX usage requires one)
- `LOG_LEVEL=INFO`

## Commands

- `/helpme`
- `/status`
- `/item`
- `/route`
- `/multiroute`
- `/advice`
- `/loadout`
- `/mining`
- `/missions`
- `/risk`
- `/trend`
- `/op`

## Notes

- UEX and Star Citizen Wiki data can change or become temporarily unavailable.
- Loadout enrichment falls back gracefully when the wiki API does not answer.
- The market snapshot command is not historical trend analysis.
