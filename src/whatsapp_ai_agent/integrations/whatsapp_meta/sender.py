import logging
from typing import Any

import httpx

from whatsapp_ai_agent.config import Settings, get_settings
from whatsapp_ai_agent.integrations.whatsapp_meta.client import (
    meta_auth_headers,
    meta_graph_api_url,
)

logger = logging.getLogger(__name__)


class MetaGraphApiError(RuntimeError):
    """A safe, structured summary of a failed Meta Graph API request."""


def _safe_graph_error_message(response: httpx.Response) -> str:
    """Expose actionable Graph error fields without logging headers or raw bodies."""

    try:
        payload = response.json()
    except ValueError:
        payload = None
    error = payload.get("error") if isinstance(payload, dict) else None
    if not isinstance(error, dict):
        return f"Meta Graph API request failed (status={response.status_code}, no structured error)"

    error_data = error.get("error_data")
    details = error_data.get("details") if isinstance(error_data, dict) else None
    fields = {
        "status": response.status_code,
        "type": error.get("type"),
        "code": error.get("code"),
        "subcode": error.get("error_subcode"),
        "message": error.get("message"),
        "details": details,
        "fbtrace_id": error.get("fbtrace_id"),
    }
    formatted = ", ".join(
        f"{name}={value}" for name, value in fields.items() if value is not None
    )
    return f"Meta Graph API request failed ({formatted})"


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
            if response.is_error:
                raise MetaGraphApiError(_safe_graph_error_message(response))
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

    async def send_typing_indicator(self, *, to: str, message_id: str) -> None:
        """Mark an inbound message read and show a typing indicator on WhatsApp.

        According to Meta's Cloud API, posting status=read with a typing_indicator
        both marks the message as read (blue ticks) and shows the user a typing
        bubble. Meta dismisses it automatically once the reply is sent, or after
        25 seconds, whichever comes first. Only use it when a reply will follow.
        """
        phone_number_id = self.settings.meta_phone_number_id
        if not phone_number_id:
            raise RuntimeError("META_PHONE_NUMBER_ID is not configured")
        recipient = "".join(char for char in str(to) if char.isdigit())
        if not recipient:
            raise ValueError("Typing indicator needs a WhatsApp recipient number")
        # The read/typing status must reference the inbound message id verbatim
        # (e.g. "wamid.HBgL..."). Meta's Cloud API does NOT accept the
        # "whatsapp:"-prefixed form here (unlike media IDs); sending the prefix
        # yields a #131009 "Parameter value is not valid" error.
        status_message_id = str(message_id)

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
                    "status": "read",
                    "message_id": status_message_id,
                    "typing_indicator": {"type": "text"},
                },
            )
            if response.is_error:
                # Typing is best-effort: never block the real reply on its failure.
                logger.warning(
                    "Meta typing indicator failed (non-fatal): %s",
                    _safe_graph_error_message(response),
                )
        finally:
            if owns_client:
                await client.aclose()

    async def send_document(
        self, *, to: str, body: str, filename: str, document_url: str
    ) -> str:
        """Send a public DOCX URL as a WhatsApp document attachment."""

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
                    "type": "document",
                    "document": {
                        "link": document_url,
                        "caption": body,
                        "filename": filename,
                    },
                },
            )
            if response.is_error:
                raise MetaGraphApiError(_safe_graph_error_message(response))
            payload: dict[str, Any] = response.json()
        finally:
            if owns_client:
                await client.aclose()

        messages = payload.get("messages")
        if not isinstance(messages, list) or not messages:
            raise RuntimeError("Meta document response did not include messages")
        message_id = messages[0].get("id") if isinstance(messages[0], dict) else None
        if not message_id:
            raise RuntimeError("Meta document response did not include a message id")
        return str(message_id)
