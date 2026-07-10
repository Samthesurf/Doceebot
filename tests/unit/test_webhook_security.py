import hmac

from whatsapp_ai_agent.config import Settings
from whatsapp_ai_agent.security.webhooks import (
    validate_meta_signature,
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


def test_meta_signature_validation_uses_raw_body_and_app_secret():
    raw_body = b'{"object":"whatsapp_business_account"}'
    app_secret = "meta-app-secret"
    signature = "sha256=" + hmac.new(
        app_secret.encode(), raw_body, "sha256"
    ).hexdigest()
    settings = Settings(
        meta_webhook_auth_enabled=True,
        meta_app_secret=app_secret,
        _env_file=None,
    )

    assert validate_meta_signature(raw_body=raw_body, signature=signature, settings=settings)
    assert not validate_meta_signature(
        raw_body=raw_body,
        signature="sha256=" + "0" * 64,
        settings=settings,
    )
    assert not validate_meta_signature(raw_body=raw_body, signature=None, settings=settings)


def test_meta_signature_bypass_is_development_only_when_explicitly_disabled():
    settings = Settings(meta_webhook_auth_enabled=False, _env_file=None)

    assert validate_meta_signature(raw_body=b"{}", signature=None, settings=settings)
