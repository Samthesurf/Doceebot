from collections.abc import Sequence

from twilio.rest import Client

from whatsapp_ai_agent.config import Settings, get_settings
from whatsapp_ai_agent.integrations.whatsapp_twilio.client import build_twilio_client


class TwilioWhatsAppSender:
    def __init__(self, client: Client | None = None, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.client = client or build_twilio_client(self.settings)

    def send_text(self, *, to: str, body: str, from_number: str | None = None) -> str:
        message = self.client.messages.create(
            from_=from_number or self.settings.twilio_whatsapp_from,
            to=to,
            body=body,
        )
        return str(message.sid)

    def send_media(
        self,
        *,
        to: str,
        body: str,
        media_urls: Sequence[str],
        from_number: str | None = None,
    ) -> str:
        message = self.client.messages.create(
            from_=from_number or self.settings.twilio_whatsapp_from,
            to=to,
            body=body,
            media_url=list(media_urls),
        )
        return str(message.sid)
