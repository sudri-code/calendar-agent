from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    database_url: str

    # Redis
    redis_url: str

    # EWS (on-premises Exchange)
    ews_verify_ssl: bool = True   # set False for self-signed corporate certs
    ews_timezone: str = "Europe/Moscow"  # IANA timezone for calendar display

    # Security
    encryption_key: str
    internal_api_key: str

    # OpenRouter
    openrouter_api_key: str
    openrouter_model: str

    # Bot
    api_base_url: str = "http://api:8000"

    # App
    environment: str = "development"
    log_level: str = "INFO"


settings = Settings()
