# Citizen AI Bot

Discord utility bot for Star Citizen with slash commands for item lookups, trade routes, risk checks, mission guidance, mining suggestions, and ship loadout recommendations enriched with Star Citizen Wiki data.

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

## Local setup

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -m citizen_ai_bot
```

## Railway deployment

Push this repo to GitHub, connect the repo in Railway, add your environment variables, and deploy. The included `Procfile` uses:

```bash
python -m citizen_ai_bot
```

## Notes

- UEX API docs currently expose `items`, `items_prices`, and `commodities_prices` under API 2.0. citeturn225036view0turn307950search0turn773908search4
- Star Citizen Wiki docs currently expose item and vehicle overviews/detail endpoints, with deprecated POST search endpoints still documented. citeturn209573search2turn209573search7
- `/loadout` is built from live Wiki vehicle/component data when the API exposes it.
