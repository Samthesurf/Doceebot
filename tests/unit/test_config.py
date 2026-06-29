import pytest
from pydantic import ValidationError

from whatsapp_ai_agent.config import Settings

APP_VALUE = "app-test-value"
TWILIO_VALUE = "twilio-test-value"
TELEGRAM_VALUE = "telegram-test-value"
PLACEHOLDER_VALUE = "change-me"


def test_development_settings_have_local_defaults():
    settings = Settings(_env_file=None)
    assert settings.app_env == "development"
    assert settings.app_timezone == "Africa/Lagos"


def test_development_allows_placeholder_webhook_values_for_local_testing():
    settings = Settings(
        telegram_webhook_secret_token=PLACEHOLDER_VALUE,
        twilio_webhook_auth_enabled=False,
        _env_file=None,
    )
    assert settings.telegram_webhook_secret_token == PLACEHOLDER_VALUE
    assert not settings.twilio_webhook_auth_enabled


def test_production_rejects_placeholder_secret():
    with pytest.raises(ValidationError):
        Settings(
            app_env="production",
            app_base_url="https://example.com",
            secret_key=PLACEHOLDER_VALUE,
            twilio_webhook_auth_enabled=True,
            twilio_auth_token=TWILIO_VALUE,
            telegram_webhook_secret_token=TELEGRAM_VALUE,
            _env_file=None,
        )


def test_production_requires_twilio_webhook_auth_enabled():
    with pytest.raises(ValidationError):
        Settings(
            app_env="production",
            app_base_url="https://example.com",
            secret_key=APP_VALUE,
            twilio_webhook_auth_enabled=False,
            twilio_auth_token=TWILIO_VALUE,
            telegram_webhook_secret_token=TELEGRAM_VALUE,
            _env_file=None,
        )


def test_production_requires_telegram_webhook_secret():
    with pytest.raises(ValidationError):
        Settings(
            app_env="production",
            app_base_url="https://example.com",
            secret_key=APP_VALUE,
            twilio_webhook_auth_enabled=True,
            twilio_auth_token=TWILIO_VALUE,
            telegram_webhook_secret_token=None,
            _env_file=None,
        )


def test_twilio_auth_requires_token_when_enabled():
    with pytest.raises(ValidationError):
        Settings(twilio_webhook_auth_enabled=True, twilio_auth_token=None, _env_file=None)
