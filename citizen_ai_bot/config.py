from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    discord_token: str = ""
    discord_guild_id: int | None = None
    log_level: str = "INFO"

    uex_api_base: str = "https://api.uexcorp.space/2.0"
    uex_api_token: str = ""

    wiki_api_base: str = "https://api.star-citizen.wiki"


settings = Settings()
