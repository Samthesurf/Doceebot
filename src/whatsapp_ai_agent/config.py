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

    meta_whatsapp_enabled: bool = False
    meta_graph_api_base_url: str = "https://graph.facebook.com"
    meta_graph_api_version: str = "v23.0"
    meta_waba_id: str | None = None
    meta_phone_number_id: str | None = None
    meta_access_token: str | None = None
    meta_app_secret: str | None = None
    meta_webhook_verify_token: str | None = None
    meta_webhook_auth_enabled: bool = False

    telegram_bot_token: str | None = None
    telegram_webhook_secret_token: str | None = None
    developer_escalation_telegram_chat_id: str | None = None
    developer_escalation_storage_dir: str = "storage/developer_escalations"

    firebase_project_id: str | None = None
    dashboard_allowed_emails: str | None = None
    dashboard_logs_password: str | None = None

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

    reminder_enabled: bool = False
    reminder_time_hour: int = Field(default=17, ge=0, le=23)
    reminder_time_minute: int = Field(default=30, ge=0, le=59)
    reminder_timezone: str = "Africa/Lagos"
    reminder_weekdays_only: bool = True

    weekly_report_enabled: bool = False
    weekly_report_time_hour: int = Field(default=17, ge=0, le=23)
    weekly_report_time_minute: int = Field(default=0, ge=0, le=59)
    weekly_report_timezone: str = "Africa/Lagos"

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

        if self.meta_webhook_auth_enabled and self.meta_app_secret in _PLACEHOLDER_VALUES:
            errors.append("META_APP_SECRET is required when Meta webhook auth is enabled")

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
            if self.meta_whatsapp_enabled:
                if not self.meta_webhook_auth_enabled:
                    errors.append(
                        "META_WEBHOOK_AUTH_ENABLED must be true when Meta WhatsApp is enabled"
                    )
                for field_name, value in {
                    "META_WABA_ID": self.meta_waba_id,
                    "META_PHONE_NUMBER_ID": self.meta_phone_number_id,
                    "META_ACCESS_TOKEN": self.meta_access_token,
                    "META_APP_SECRET": self.meta_app_secret,
                    "META_WEBHOOK_VERIFY_TOKEN": self.meta_webhook_verify_token,
                }.items():
                    if value in _PLACEHOLDER_VALUES:
                        errors.append(f"{field_name} must be set when Meta WhatsApp is enabled")

        if errors:
            raise ValueError("; ".join(errors))
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
