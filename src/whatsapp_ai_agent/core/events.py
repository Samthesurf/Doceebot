from datetime import UTC, date, datetime, time
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class MediaRef(BaseModel):
    platform_media_id: str | None = None
    url: str | None = None
    content_type: str | None = None
    filename: str | None = None
    size_bytes: int | None = None
    index: int = 0
    storage_backend: str | None = None
    storage_key: str | None = None
    storage_url: str | None = None
    sha256_hex: str | None = None


class LocationRef(BaseModel):
    source: Literal[
        "explicit_pin",
        "text_inferred",
        "active_site",
        "company_site",
        "manual_correction",
    ]
    latitude: float | None = None
    longitude: float | None = None
    address: str | None = None
    label: str | None = None
    site_id: UUID | None = None
    site_name: str | None = None
    confidence: float = Field(ge=0, le=1)
    needs_confirmation: bool = False


class InboundEvent(BaseModel):
    org_id: UUID | None = None
    user_id: UUID | None = None
    platform: Literal["telegram", "whatsapp_twilio"]
    platform_message_id: str
    platform_user_id: str
    platform_chat_id: str
    message_type: Literal["text", "voice", "audio", "image", "document", "location", "unknown"]
    text: str | None = None
    media: list[MediaRef] = Field(default_factory=list)
    location: LocationRef | None = None
    platform_timestamp: datetime | None = None
    received_at: datetime
    local_date: date
    local_time: time
    timezone: str
    raw_payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("received_at", "platform_timestamp")
    @classmethod
    def ensure_aware_datetime(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value
