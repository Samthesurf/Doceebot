from collections.abc import Mapping
from datetime import datetime
from pathlib import PurePosixPath
from typing import Any

from whatsapp_ai_agent.core.events import InboundEvent, LocationRef, MediaRef
from whatsapp_ai_agent.core.timestamps import local_date_and_time, utc_now


def _as_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text != "" else None


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _filename_from_url(url: str | None) -> str | None:
    if not url:
        return None
    name = PurePosixPath(url.split("?", 1)[0]).name
    return name or None


def _message_type(body: str | None, media: list[MediaRef], location: LocationRef | None) -> str:
    if location is not None and not media and not body:
        return "location"
    if not media:
        return "text" if body else "unknown"

    content_type = (media[0].content_type or "").lower()
    if content_type.startswith("image/"):
        return "image"
    if content_type.startswith("audio/ogg") or content_type.startswith("audio/amr"):
        return "voice"
    if content_type.startswith("audio/"):
        return "audio"
    return "document"


def parse_twilio_whatsapp_form(
    payload: Mapping[str, Any],
    *,
    received_at: datetime | None = None,
    timezone_name: str = "Africa/Lagos",
) -> InboundEvent:
    """Convert Twilio WhatsApp form fields into the shared InboundEvent shape."""

    received_at = received_at or utc_now()
    local_date, local_time = local_date_and_time(received_at, timezone_name)

    message_sid = _as_text(payload.get("MessageSid")) or _as_text(payload.get("SmsMessageSid"))
    if not message_sid:
        raise ValueError("Twilio payload is missing MessageSid")

    body = _as_text(payload.get("Body"))
    from_id = _as_text(payload.get("From")) or _as_text(payload.get("WaId"))
    if not from_id:
        raise ValueError("Twilio payload is missing From")

    media: list[MediaRef] = []
    for index in range(_as_int(payload.get("NumMedia"), 0)):
        url = _as_text(payload.get(f"MediaUrl{index}"))
        content_type = _as_text(payload.get(f"MediaContentType{index}"))
        if not url and not content_type:
            continue
        media.append(
            MediaRef(
                platform_media_id=_filename_from_url(url),
                url=url,
                content_type=content_type,
                filename=_filename_from_url(url),
                size_bytes=_as_int(payload.get(f"MediaSize{index}"), 0) or None,
                index=index,
            )
        )

    latitude = _as_float(payload.get("Latitude"))
    longitude = _as_float(payload.get("Longitude"))
    location = None
    if latitude is not None or longitude is not None:
        location = LocationRef(
            source="explicit_pin",
            latitude=latitude,
            longitude=longitude,
            address=_as_text(payload.get("Address")),
            label=_as_text(payload.get("Label")),
            confidence=1.0,
        )

    return InboundEvent(
        platform="whatsapp_twilio",
        platform_message_id=message_sid,
        platform_user_id=_as_text(payload.get("WaId")) or from_id,
        platform_chat_id=from_id,
        message_type=_message_type(body, media, location),
        text=body,
        media=media,
        location=location,
        received_at=received_at,
        local_date=local_date,
        local_time=local_time,
        timezone=timezone_name,
        raw_payload={str(key): value for key, value in payload.items()},
    )
