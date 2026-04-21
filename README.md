# Citizen AI Bot

Discord utility bot for Star Citizen with slash commands for item lookups, trade routes, risk checks, mission guidance, mining suggestions, and a wiki-driven `/loadout` command.

## Highlights

- Deployable repo structure
- Railway-ready `Procfile`
- `.env.example` for first-time setup
- `/status` checks both UEX and the Star Citizen Wiki API
- `/loadout` now builds from Star Citizen Wiki vehicle data instead of curated static ship blurbs

## Local setup

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env       # Windows: copy .env.example .env
python -m citizen_ai_bot
```

## Environment variables

- `DISCORD_TOKEN`
- `DISCORD_GUILD_ID` (optional)
- `UEX_API_TOKEN` (optional)
- `LOG_LEVEL=INFO`
- `REQUEST_TIMEOUT_SECONDS=25`

## Notes on `/loadout`

The loadout report uses the Star Citizen Wiki API vehicle endpoints and builds its output from the vehicle record, mounted components, exposed port data, and visible weapon stats. When the API only exposes installed items rather than every compatible item, the report reflects the strongest named setup visible from that response.
