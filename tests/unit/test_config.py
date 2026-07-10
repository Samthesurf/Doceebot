import pytest
from pydantic import ValidationError

from whatsapp_ai_agent.config import Settings

APP_VALUE = "app-test-value"
TWILIO_VALUE = "twilio-test-value"
TELEGRAM_VALUE = "telegram-test-value"
META_VALUE = "meta-test-value"
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


def test_r2_media_backend_requires_account_and_bucket():
    with pytest.raises(ValidationError):
        Settings(media_storage_backend="r2", cloudflare_account_id=None, _env_file=None)


def test_cloudflare_r2_endpoint_defaults_from_account_id():
    settings = Settings(cloudflare_account_id="account-1", _env_file=None)

    assert settings.r2_endpoint_url == "https://account-1.r2.cloudflarestorage.com"


def test_enabled_meta_configuration_is_available_in_production():
    settings = Settings(
        app_env="production",
        app_base_url="https://example.com",
        secret_key=APP_VALUE,
        twilio_webhook_auth_enabled=True,
        twilio_auth_token=TWILIO_VALUE,
        telegram_webhook_secret_token=TELEGRAM_VALUE,
        meta_whatsapp_enabled=True,
        meta_webhook_auth_enabled=True,
        meta_waba_id="9876543210987654",
        meta_app_secret=META_VALUE,
        meta_webhook_verify_token=META_VALUE,
        meta_access_token=META_VALUE,
        meta_phone_number_id="1234567890123456",
        _env_file=None,
    )

    assert settings.meta_whatsapp_enabled
    assert settings.meta_phone_number_id == "1234567890123456"


@pytest.mark.parametrize(
    "field,value",
    [
        ("meta_webhook_auth_enabled", False),
        ("meta_waba_id", None),
        ("meta_app_secret", None),
        ("meta_webhook_verify_token", None),
        ("meta_access_token", None),
        ("meta_phone_number_id", None),
    ],
)
def test_enabled_meta_configuration_requires_secure_production_values(field, value):
    values = {
        "app_env": "production",
        "app_base_url": "https://example.com",
        "secret_key": APP_VALUE,
        "twilio_webhook_auth_enabled": True,
        "twilio_auth_token": TWILIO_VALUE,
        "telegram_webhook_secret_token": TELEGRAM_VALUE,
        "meta_whatsapp_enabled": True,
        "meta_webhook_auth_enabled": True,
        "meta_waba_id": "9876543210987654",
        "meta_app_secret": META_VALUE,
        "meta_webhook_verify_token": META_VALUE,
        "meta_access_token": META_VALUE,
        "meta_phone_number_id": "1234567890123456",
        "_env_file": None,
    }
    values[field] = value

    with pytest.raises(ValidationError):
        Settings(**values)
