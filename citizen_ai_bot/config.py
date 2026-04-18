from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    discord_token: str = Field(default="", alias="DISCORD_TOKEN")
    discord_guild_id: int | None = Field(default=None, alias="DISCORD_GUILD_ID")
    uex_api_token: str = Field(default="", alias="UEX_API_TOKEN")
    uex_api_base: str = Field(default="https://api.uexcorp.space/2.0", alias="UEX_API_BASE")
    request_timeout_seconds: float = Field(default=25.0, alias="REQUEST_TIMEOUT_SECONDS")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")


settings = Settings()
