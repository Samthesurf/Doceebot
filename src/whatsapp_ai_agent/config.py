from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from whatsapp_ai_agent import __version__

_PLACEHOLDER_VALUES = {None, "", "change-me"}


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "WhatsApp AI Agent"
    app_version: str = __version__
    app_env: Literal["development", "test", "production"] = "development"
    app_base_url: str = "http://localhost:8000"
    app_timezone: str = "Africa/Lagos"
    secret_key: str = "change-me"

    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/whatsapp_ai_agent"
    redis_url: str = "redis://localhost:6379/0"

    twilio_account_sid: str | None = None
    twilio_auth_token: str | None = None
    twilio_whatsapp_from: str | None = None
    twilio_messaging_service_sid: str | None = None
    twilio_webhook_auth_enabled: bool = False

    telegram_bot_token: str | None = None
    telegram_webhook_secret_token: str | None = None

    gemini_api_key: str | None = None
    gemini_model: str = "gemini-3.1-flash-lite"
    deepseek_api_key: str | None = None
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-v4-flash"

    cloudflare_api_base_url: str = "https://api.cloudflare.com/client/v4"
    cloudflare_account_id: str | None = None
    cloudflare_api_token: str | None = None
    cloudflare_r2_bucket: str | None = None
    cloudflare_r2_public_base_url: str | None = None
    cloudflare_r2_access_key_id: str | None = None
    cloudflare_r2_secret_access_key: str | None = None
    cloudflare_r2_endpoint_url: str | None = None
    cloudflare_ai_search_instance: str | None = None
    cloudflare_ai_search_namespace: str | None = None
    cloudflare_ai_search_instance_prefix: str = "org"
    cloudflare_ai_search_max_results: int = Field(default=8, ge=1, le=50)
    rag_backend: str = "cloudflare_ai_search"
    rag_embedding_model: str = "@cf/baai/bge-base-en-v1.5"

    media_storage_backend: Literal["local", "r2"] = "local"
    local_storage_dir: str = "storage"
    public_media_base_url: str | None = None

    location_features_enabled: bool = True
    location_tracking_mode: Literal["explicit_only"] = "explicit_only"
    location_session_ttl_hours: int = Field(default=8, ge=1)
    location_low_confidence_threshold: float = Field(default=0.70, ge=0, le=1)
    location_geocoder_provider: str = "openstreetmap"
    location_ask_when_unclear: bool = True

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"

    @property
    def r2_endpoint_url(self) -> str | None:
        if self.cloudflare_r2_endpoint_url:
            return self.cloudflare_r2_endpoint_url.rstrip("/")
        if self.cloudflare_account_id:
            return f"https://{self.cloudflare_account_id}.r2.cloudflarestorage.com"
        return None

    @model_validator(mode="after")
    def validate_security_settings(self) -> "Settings":
        errors: list[str] = []

        if self.twilio_webhook_auth_enabled and self.twilio_auth_token in _PLACEHOLDER_VALUES:
            errors.append("TWILIO_AUTH_TOKEN is required when Twilio webhook auth is enabled")

        if self.media_storage_backend == "r2":
            if self.cloudflare_account_id in _PLACEHOLDER_VALUES:
                errors.append("CLOUDFLARE_ACCOUNT_ID is required when MEDIA_STORAGE_BACKEND=r2")
            if self.cloudflare_r2_bucket in _PLACEHOLDER_VALUES:
                errors.append("CLOUDFLARE_R2_BUCKET is required when MEDIA_STORAGE_BACKEND=r2")

        if self.is_production:
            if self.secret_key in _PLACEHOLDER_VALUES:
                errors.append("SECRET_KEY must be set in production")
            if not self.app_base_url.startswith("https://"):
                errors.append("APP_BASE_URL must be HTTPS in production")
            if not self.twilio_webhook_auth_enabled:
                errors.append("TWILIO_WEBHOOK_AUTH_ENABLED must be true in production")
            if self.telegram_webhook_secret_token in _PLACEHOLDER_VALUES:
                errors.append("TELEGRAM_WEBHOOK_SECRET_TOKEN must be set in production")

        if errors:
            raise ValueError("; ".join(errors))
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
