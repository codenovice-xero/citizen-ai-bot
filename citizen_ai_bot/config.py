from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()


@dataclass(slots=True)
class Settings:
    discord_token: str = os.getenv("DISCORD_TOKEN", "")
    discord_guild_id: str = os.getenv("DISCORD_GUILD_ID", "")
    uex_api_token: str = os.getenv("UEX_API_TOKEN", "")
    uex_api_base: str = os.getenv("UEX_API_BASE", "https://api.uexcorp.space/2.0")
    request_timeout_seconds: float = float(os.getenv("REQUEST_TIMEOUT_SECONDS", "20"))

    @property
    def guild_id_int(self) -> int | None:
        if not self.discord_guild_id.strip():
            return None
        return int(self.discord_guild_id)


settings = Settings()
