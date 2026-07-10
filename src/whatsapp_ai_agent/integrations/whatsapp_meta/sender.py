from typing import Any

import httpx

from whatsapp_ai_agent.config import Settings, get_settings
from whatsapp_ai_agent.integrations.whatsapp_meta.client import (
    meta_auth_headers,
    meta_graph_api_url,
)


class MetaWhatsAppSender:
    """Send WhatsApp Cloud API messages directly through Meta Graph API."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.http_client = http_client

    async def send_text(self, *, to: str, body: str) -> str:
        phone_number_id = self.settings.meta_phone_number_id
        if not phone_number_id:
            raise RuntimeError("META_PHONE_NUMBER_ID is not configured")
        recipient = "".join(char for char in str(to) if char.isdigit())
        if not recipient:
            raise ValueError("Meta WhatsApp recipient must contain a phone number")

        owns_client = self.http_client is None
        client = self.http_client or httpx.AsyncClient(timeout=30.0)
        try:
            response = await client.post(
                meta_graph_api_url(self.settings, phone_number_id, "messages"),
                headers={
                    **meta_auth_headers(self.settings),
                    "Content-Type": "application/json",
                },
                json={
                    "messaging_product": "whatsapp",
                    "recipient_type": "individual",
                    "to": recipient,
                    "type": "text",
                    "text": {"body": body},
                },
            )
            response.raise_for_status()
            payload: dict[str, Any] = response.json()
        finally:
            if owns_client:
                await client.aclose()

        messages = payload.get("messages")
        if not isinstance(messages, list) or not messages:
            raise RuntimeError("Meta send response did not include messages")
        message_id = messages[0].get("id") if isinstance(messages[0], dict) else None
        if not message_id:
            raise RuntimeError("Meta send response did not include a message id")
        return str(message_id)
