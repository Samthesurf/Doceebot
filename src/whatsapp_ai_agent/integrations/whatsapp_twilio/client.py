from twilio.rest import Client

from whatsapp_ai_agent.config import Settings, get_settings


def build_twilio_client(settings: Settings | None = None) -> Client:
    settings = settings or get_settings()
    if not settings.twilio_account_sid or not settings.twilio_auth_token:
        raise RuntimeError("Twilio credentials are not configured")
    return Client(settings.twilio_account_sid, settings.twilio_auth_token)
