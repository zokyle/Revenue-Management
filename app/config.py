from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "sqlite:///./revenue_management.db"
    secret_key: str = "change-me-in-production"
    debug: bool = True
    app_name: str = "Hotel Revenue Management"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
