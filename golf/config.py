"""Settings for the Caddie golf strategy app.

Kept separate from the hotel app's settings so the two applications can run
side by side with independent databases and environment variables.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class GolfSettings(BaseSettings):
    golf_database_url: str = "sqlite:///./golf_caddie.db"
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-opus-5"
    monte_carlo_samples: int = 400
    debug: bool = False
    app_name: str = "Caddie - Golf Strategy Agent"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = GolfSettings()
