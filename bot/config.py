from pydantic_settings import BaseSettings, SettingsConfigDict


class BotSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    bot_token: str = ""
    bot_webhook_secret: str = ""
    bot_webhook_url: str = ""

    redis_url: str = "redis://redis:6379/0"
    api_base_url: str = "http://api:8000"
    internal_api_key: str = "internal-key"

    environment: str = "development"
    log_level: str = "INFO"


bot_settings = BotSettings()
