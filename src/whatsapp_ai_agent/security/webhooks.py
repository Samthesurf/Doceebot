from collections.abc import Mapping
from hashlib import sha256
from hmac import compare_digest, new

from twilio.request_validator import RequestValidator

from whatsapp_ai_agent.config import Settings, get_settings

_PLACEHOLDER_VALUES = {None, "", "change-me"}


def validate_twilio_request(
    *,
    url: str,
    form: Mapping[str, str],
    signature: str | None,
    settings: Settings | None = None,
) -> bool:
    settings = settings or get_settings()
    if not settings.twilio_webhook_auth_enabled:
        return not settings.is_production
    if not signature or not settings.twilio_auth_token:
        return False
    return RequestValidator(settings.twilio_auth_token).validate(url, dict(form), signature)


def validate_meta_signature(
    *,
    raw_body: bytes,
    signature: str | None,
    settings: Settings | None = None,
) -> bool:
    """Validate Meta's ``X-Hub-Signature-256`` against the exact raw body."""

    settings = settings or get_settings()
    if not settings.meta_webhook_auth_enabled:
        return not settings.is_production
    app_secret = settings.meta_app_secret
    if not signature or app_secret in _PLACEHOLDER_VALUES:
        return False
    assert app_secret is not None
    expected = "sha256=" + new(app_secret.encode("utf-8"), raw_body, sha256).hexdigest()
    return compare_digest(signature, expected)


def validate_telegram_secret_header(
    *,
    header_value: str | None,
    settings: Settings | None = None,
) -> bool:
    settings = settings or get_settings()
    expected = settings.telegram_webhook_secret_token
    if expected in _PLACEHOLDER_VALUES:
        return not settings.is_production
    if header_value is None:
        return False
    return compare_digest(header_value, expected)
