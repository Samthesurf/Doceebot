from datetime import UTC, datetime
from typing import Any

from whatsapp_ai_agent.core.events import InboundEvent, LocationRef, MediaRef
from whatsapp_ai_agent.core.timestamps import local_date_and_time, utc_now


def _message_from_update(update: dict[str, Any]) -> dict[str, Any]:
    message = update.get("message") or update.get("edited_message")
    if not isinstance(message, dict):
        raise ValueError("Telegram update does not contain a message")
    return message


def _platform_timestamp(message: dict[str, Any]) -> datetime | None:
    value = message.get("date")
    if value is None:
        return None
    return datetime.fromtimestamp(int(value), tz=UTC)


def _media_from_message(message: dict[str, Any]) -> tuple[str, list[MediaRef], str | None]:
    if "voice" in message:
        voice = message["voice"]
        return (
            "voice",
            [
                MediaRef(
                    platform_media_id=voice.get("file_id"),
                    content_type=voice.get("mime_type"),
                    size_bytes=voice.get("file_size"),
                    index=0,
                )
            ],
            None,
        )
    if "photo" in message and message["photo"]:
        photo = message["photo"][-1]
        return (
            "image",
            [
                MediaRef(
                    platform_media_id=photo.get("file_id"),
                    content_type="image/jpeg",
                    size_bytes=photo.get("file_size"),
                    index=0,
                )
            ],
            message.get("caption"),
        )
    if "document" in message:
        document = message["document"]
        return (
            "document",
            [
                MediaRef(
                    platform_media_id=document.get("file_id"),
                    content_type=document.get("mime_type"),
                    filename=document.get("file_name"),
                    size_bytes=document.get("file_size"),
                    index=0,
                )
            ],
            message.get("caption"),
        )
    return "text", [], message.get("text")


def _location_from_message(message: dict[str, Any]) -> LocationRef | None:
    location = message.get("location")
    label = None
    address = None
    if not location and "venue" in message:
        venue = message["venue"]
        location = venue.get("location")
        label = venue.get("title")
        address = venue.get("address")
    if not location:
        return None
    return LocationRef(
        source="explicit_pin",
        latitude=location.get("latitude"),
        longitude=location.get("longitude"),
        label=label,
        address=address,
        confidence=1.0,
    )


def parse_telegram_update(
    update: dict[str, Any],
    *,
    received_at: datetime | None = None,
    timezone_name: str = "Africa/Lagos",
) -> InboundEvent:
    message = _message_from_update(update)
    received_at = received_at or utc_now()
    platform_timestamp = _platform_timestamp(message)
    local_date, local_time = local_date_and_time(platform_timestamp or received_at, timezone_name)

    chat = message.get("chat") or {}
    sender = message.get("from") or {}
    message_id = message.get("message_id")
    if message_id is None:
        raise ValueError("Telegram message is missing message_id")
    if chat.get("id") is None:
        raise ValueError("Telegram message is missing chat.id")
    if sender.get("id") is None:
        raise ValueError("Telegram message is missing from.id")

    location = _location_from_message(message)
    message_type, media, text = _media_from_message(message)
    if location is not None and not media and not text:
        message_type = "location"

    platform_chat_id = str(chat["id"])
    return InboundEvent(
        platform="telegram",
        platform_message_id=f"{platform_chat_id}:{message_id}",
        platform_user_id=str(sender["id"]),
        platform_chat_id=platform_chat_id,
        message_type=message_type,
        text=text,
        media=media,
        location=location,
        platform_timestamp=platform_timestamp,
        received_at=received_at,
        local_date=local_date,
        local_time=local_time,
        timezone=timezone_name,
        raw_payload=update,
    )
