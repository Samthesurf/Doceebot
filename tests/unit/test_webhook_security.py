from whatsapp_ai_agent.config import Settings
from whatsapp_ai_agent.security.webhooks import (
    validate_telegram_secret_header,
    validate_twilio_request,
)

TELEGRAM_VALUE = "telegram-test-value"
PLACEHOLDER_VALUE = "change-me"


def test_telegram_secret_header_uses_configured_secret():
    settings = Settings(telegram_webhook_secret_token=TELEGRAM_VALUE, _env_file=None)

    assert validate_telegram_secret_header(
        header_value=TELEGRAM_VALUE,
        settings=settings,
    )
    assert not validate_telegram_secret_header(
        header_value="wrong-value",
        settings=settings,
    )


def test_telegram_placeholder_secret_is_disabled_only_outside_production():
    settings = Settings(telegram_webhook_secret_token=PLACEHOLDER_VALUE, _env_file=None)

    assert validate_telegram_secret_header(header_value=None, settings=settings)


def test_twilio_signature_validation_disabled_only_outside_production():
    settings = Settings(twilio_webhook_auth_enabled=False, _env_file=None)

    assert validate_twilio_request(
        url="https://example.com/webhooks/twilio/whatsapp",
        form={},
        signature=None,
        settings=settings,
    )
