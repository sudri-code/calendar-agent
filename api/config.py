from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    database_url: str = "postgresql+asyncpg://calendar_bot:changeme@localhost:5432/calendar_bot"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # EWS (on-premises Exchange)
    ews_verify_ssl: bool = True   # set False for self-signed corporate certs

    # Security
    encryption_key: str = ""
    internal_api_key: str = "internal-key"

    # OpenRouter
    openrouter_api_key: str = ""
    openrouter_model: str = "anthropic/claude-3-haiku"

    # Bot
    api_base_url: str = "http://api:8000"

    # App
    environment: str = "development"
    log_level: str = "INFO"


settings = Settings()
