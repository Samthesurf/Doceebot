from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, Literal

from whatsapp_ai_agent.core.events import InboundEvent, LocationRef, MediaRef
from whatsapp_ai_agent.core.timestamps import local_date_and_time, utc_now

MessageType = Literal["text", "voice", "audio", "image", "video", "document", "location", "unknown"]


def _as_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _platform_timestamp(message: Mapping[str, Any]) -> datetime | None:
    value = message.get("timestamp")
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(int(str(value)), tz=UTC)
    except (TypeError, ValueError, OverflowError):
        return None


def _media_message(
    message: Mapping[str, Any],
) -> tuple[MessageType, list[MediaRef], str | None]:
    message_kind = _as_text(message.get("type")) or "unknown"
    if message_kind == "text":
        return "text", [], _as_text(_mapping(message.get("text")).get("body"))

    if message_kind == "location":
        return "location", [], None

    content = _mapping(message.get(message_kind))
    if message_kind not in {"image", "audio", "video", "document", "sticker"}:
        return "unknown", [], None
    if not content:
        raise ValueError(f"Meta {message_kind} message is missing its content object")

    media_id = _as_text(content.get("id"))
    if not media_id:
        raise ValueError(f"Meta {message_kind} message is missing media id")

    content_type = _as_text(content.get("mime_type"))
    if message_kind == "sticker":
        content_type = content_type or "image/webp"
    if message_kind == "audio":
        message_type: MessageType = "voice" if content.get("voice") else "audio"
    elif message_kind == "sticker":
        message_type = "image"
    elif message_kind == "image":
        message_type = "image"
    elif message_kind == "video":
        message_type = "video"
    else:
        message_type = "document"

    return (
        message_type,
        [
            MediaRef(
                platform_media_id=media_id,
                content_type=content_type,
                filename=_as_text(content.get("filename")),
                index=0,
            )
        ],
        _as_text(content.get("caption")),
    )


def _location_from_message(message: Mapping[str, Any]) -> LocationRef | None:
    location = _mapping(message.get("location"))
    if not location:
        return None
    latitude = location.get("latitude")
    longitude = location.get("longitude")
    if latitude is None and longitude is None:
        raise ValueError("Meta location message is missing latitude and longitude")
    try:
        parsed_latitude = float(latitude) if latitude is not None else None
        parsed_longitude = float(longitude) if longitude is not None else None
    except (TypeError, ValueError) as exc:
        raise ValueError("Meta location message has invalid coordinates") from exc
    return LocationRef(
        source="explicit_pin",
        latitude=parsed_latitude,
        longitude=parsed_longitude,
        label=_as_text(location.get("name")),
        address=_as_text(location.get("address")),
        confidence=1.0,
    )


def _iter_inbound_messages(payload: Mapping[str, Any]):
    entries = payload.get("entry")
    if not isinstance(entries, list):
        return
    for entry in entries:
        for change in _mapping(entry).get("changes", []):
            change_mapping = _mapping(change)
            if change_mapping.get("field") != "messages":
                continue
            value = _mapping(change_mapping.get("value"))
            messages = value.get("messages")
            if not isinstance(messages, list):
                continue
            for message in messages:
                if isinstance(message, Mapping):
                    yield message


def parse_meta_webhook_payload(
    payload: Mapping[str, Any],
    *,
    received_at: datetime | None = None,
    timezone_name: str = "Africa/Lagos",
) -> list[InboundEvent]:
    """Normalize inbound Meta WhatsApp Cloud API messages into shared events.

    Delivery/read status callbacks contain ``statuses`` rather than ``messages``
    and intentionally return no events because they are not inbound user content.
    """

    if payload.get("object") != "whatsapp_business_account":
        return []

    received_at = received_at or utc_now()
    events: list[InboundEvent] = []
    for message in _iter_inbound_messages(payload):
        sender = _as_text(message.get("from"))
        message_id = _as_text(message.get("id"))
        if not sender:
            raise ValueError("Meta message is missing from")
        if not message_id:
            raise ValueError("Meta message is missing id")

        platform_timestamp = _platform_timestamp(message)
        local_date, local_time = local_date_and_time(
            platform_timestamp or received_at,
            timezone_name,
        )
        message_type, media, text = _media_message(message)
        location = _location_from_message(message)
        if location is not None and not media and not text:
            message_type = "location"

        events.append(
            InboundEvent(
                platform="whatsapp_meta",
                platform_message_id=message_id,
                platform_user_id=sender,
                platform_chat_id=sender,
                message_type=message_type,
                text=text,
                media=media,
                location=location,
                platform_timestamp=platform_timestamp,
                received_at=received_at,
                local_date=local_date,
                local_time=local_time,
                timezone=timezone_name,
                raw_payload={str(key): value for key, value in payload.items()},
            )
        )
    return events
