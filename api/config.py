from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    database_url: str = "postgresql+asyncpg://calendar_bot:changeme@localhost:5432/calendar_bot"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Microsoft OAuth
    ms_client_id: str = ""
    ms_client_secret: str = ""
    ms_redirect_uri: str = "http://localhost:8000/api/v1/accounts/oauth/callback"
    ms_tenant_id: str = "common"
    ms_scopes: str = "User.Read offline_access Calendars.ReadWrite Calendars.ReadWrite.Shared Contacts.Read"

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

    @property
    def ms_scopes_list(self) -> list[str]:
        return self.ms_scopes.split()


settings = Settings()
