# Citizen AI Bot

Clean rebuild of the Citizen AI Discord bot for Star Citizen.

## Commands
- /helpme
- /status
- /item
- /route
- /multiroute
- /advice
- /loadout
- /mining
- /missions
- /risk
- /trend
- /op

## Setup
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -m citizen_ai_bot
