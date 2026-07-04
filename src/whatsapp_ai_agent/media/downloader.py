from __future__ import annotations

import mimetypes
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Protocol
from urllib.parse import quote, urlparse

import httpx

from whatsapp_ai_agent.config import Settings, get_settings
from whatsapp_ai_agent.core.events import InboundEvent, MediaRef
from whatsapp_ai_agent.media.storage import (
    StoredObject,
    get_media_storage,
    normalize_object_key,
    org_object_key,
)


class MediaDownloadError(RuntimeError):
    """Raised when a platform media object cannot be downloaded."""


@dataclass(frozen=True)
class DownloadedMedia:
    media: MediaRef
    data: bytes
    content_type: str | None = None
    filename: str | None = None


@dataclass(frozen=True)
class StoredInboundMedia:
    original: MediaRef
    media: MediaRef
    data: bytes
    stored: StoredObject


class MediaDownloader(Protocol):
    async def download(self, media: MediaRef) -> DownloadedMedia: ...


def _clean_content_type(value: str | None) -> str | None:
    if not value:
        return None
    return value.split(";", 1)[0].strip() or None


_GENERIC_CONTENT_TYPES = {"application/octet-stream", "binary/octet-stream"}


def _is_generic_content_type(value: str | None) -> bool:
    return (value or "").lower() in _GENERIC_CONTENT_TYPES


def _best_content_type(
    *,
    response_content_type: str | None,
    platform_content_type: str | None,
    filename: str | None,
) -> str | None:
    """Pick the most specific content type available for a platform file.

    Telegram often serves uploaded documents as application/octet-stream even
    when the original filename has a useful extension such as .xlsx or .docx.
    Prefer the platform-declared MIME type, then the filename-derived MIME type,
    before falling back to a generic HTTP response type.
    """

    response_clean = _clean_content_type(response_content_type)
    platform_clean = _clean_content_type(platform_content_type)
    filename_guess = mimetypes.guess_type(filename or "")[0]

    for candidate in (platform_clean, filename_guess, response_clean):
        if candidate and not _is_generic_content_type(candidate):
            return candidate
    return response_clean or platform_clean or filename_guess


def _safe_component(value: str | None, *, fallback: str) -> str:
    text = (value or fallback).strip() or fallback
    text = PurePosixPath(text.replace("\\", "/")).name or fallback
    text = re.sub(r"[^A-Za-z0-9._:-]+", "_", text).strip("._")
    return text or fallback


def _filename_from_content_type(content_type: str | None, *, fallback: str) -> str:
    suffix = mimetypes.guess_extension(content_type or "") or ""
    if suffix == ".jpe":
        suffix = ".jpg"
    return f"{fallback}{suffix}"


def media_kind_from_content_type(content_type: str | None, fallback: str = "document") -> str:
    content = (content_type or "").lower()
    if content.startswith("image/"):
        return "image"
    if content.startswith("audio/"):
        return "voice" if "ogg" in content or "amr" in content else "audio"
    if content.startswith("text/") or content in {
        "application/pdf",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.ms-excel",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }:
        return "document"
    return fallback


class TelegramMediaDownloader:
    def __init__(
        self,
        settings: Settings | None = None,
        *,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.http_client = http_client

    async def download(self, media: MediaRef) -> DownloadedMedia:
        if not media.platform_media_id:
            raise MediaDownloadError("Telegram media is missing platform_media_id")
        if not self.settings.telegram_bot_token:
            raise MediaDownloadError("TELEGRAM_BOT_TOKEN is not configured")

        owns_client = self.http_client is None
        client = self.http_client or httpx.AsyncClient(timeout=30.0, follow_redirects=True)
        try:
            metadata_response = await client.post(
                f"https://api.telegram.org/bot{self.settings.telegram_bot_token}/getFile",
                data={"file_id": media.platform_media_id},
            )
            metadata_response.raise_for_status()
            metadata = metadata_response.json()
            if not metadata.get("ok"):
                description = metadata.get("description") or "Telegram getFile returned ok=false"
                raise MediaDownloadError(str(description))
            file_path = metadata.get("result", {}).get("file_path")
            if not file_path:
                raise MediaDownloadError(
                    "Telegram getFile response did not include result.file_path"
                )

            file_response = await client.get(
                "https://api.telegram.org/file/"
                f"bot{self.settings.telegram_bot_token}/{quote(file_path, safe='/')}"
            )
            file_response.raise_for_status()
        finally:
            if owns_client:
                await client.aclose()

        filename = media.filename or PurePosixPath(file_path).name
        content_type = _best_content_type(
            response_content_type=file_response.headers.get("content-type"),
            platform_content_type=media.content_type,
            filename=filename,
        )
        if not filename:
            filename = _filename_from_content_type(content_type, fallback=f"telegram-{media.index}")
        return DownloadedMedia(
            media=media,
            data=file_response.content,
            content_type=content_type,
            filename=filename,
        )


class TwilioMediaDownloader:
    def __init__(
        self,
        settings: Settings | None = None,
        *,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.http_client = http_client

    async def download(self, media: MediaRef) -> DownloadedMedia:
        if not media.url:
            raise MediaDownloadError("Twilio media is missing URL")

        owns_client = self.http_client is None
        client = self.http_client or httpx.AsyncClient(timeout=30.0, follow_redirects=True)
        auth: tuple[str, str] | None = None
        if self.settings.twilio_account_sid and self.settings.twilio_auth_token:
            auth = (self.settings.twilio_account_sid, self.settings.twilio_auth_token)
        try:
            response = await client.get(media.url, auth=auth)
            response.raise_for_status()
        finally:
            if owns_client:
                await client.aclose()

        parsed = urlparse(media.url)
        filename = media.filename or PurePosixPath(parsed.path).name
        content_type = _best_content_type(
            response_content_type=response.headers.get("content-type"),
            platform_content_type=media.content_type,
            filename=filename,
        )
        if not filename:
            filename = _filename_from_content_type(content_type, fallback=f"twilio-{media.index}")
        return DownloadedMedia(
            media=media,
            data=response.content,
            content_type=content_type,
            filename=filename,
        )


def downloader_for_event(
    event: InboundEvent,
    settings: Settings | None = None,
    *,
    telegram_http_client: httpx.AsyncClient | None = None,
    twilio_http_client: httpx.AsyncClient | None = None,
) -> MediaDownloader:
    if event.platform == "telegram":
        return TelegramMediaDownloader(settings, http_client=telegram_http_client)
    if event.platform == "whatsapp_twilio":
        return TwilioMediaDownloader(settings, http_client=twilio_http_client)
    raise MediaDownloadError(f"Unsupported media platform: {event.platform}")


def inbound_media_storage_key(event: InboundEvent, media: MediaRef, filename: str | None) -> str:
    fallback_name = _filename_from_content_type(
        media.content_type,
        fallback=f"upload-{media.index}",
    )
    safe_filename = _safe_component(filename or media.filename, fallback=fallback_name)
    safe_message_id = _safe_component(event.platform_message_id, fallback="message")
    key_parts: Sequence[str] = (
        "media",
        event.platform,
        event.local_date.isoformat(),
        safe_message_id,
        f"{media.index}-{safe_filename}",
    )
    if event.org_id:
        return org_object_key(str(event.org_id), *key_parts)
    return normalize_object_key("/".join(("unresolved", *key_parts)))


def store_downloaded_media(
    event: InboundEvent,
    downloaded: DownloadedMedia,
    *,
    settings: Settings | None = None,
) -> StoredInboundMedia:
    settings = settings or get_settings()
    content_type = downloaded.content_type or downloaded.media.content_type
    filename = downloaded.filename or downloaded.media.filename
    key = inbound_media_storage_key(event, downloaded.media, filename)
    stored = get_media_storage(settings).save_bytes(
        key,
        downloaded.data,
        content_type=content_type,
        metadata={
            "org_id": str(event.org_id) if event.org_id else "unresolved",
            "source_type": "inbound_media",
            "platform": event.platform,
            "platform_message_id": event.platform_message_id,
            "platform_media_id": downloaded.media.platform_media_id or "",
        },
    )
    media = downloaded.media.model_copy(
        update={
            "content_type": content_type,
            "filename": filename,
            "size_bytes": len(downloaded.data),
            "storage_backend": stored.backend,
            "storage_key": stored.key,
            "storage_url": stored.url,
            "sha256_hex": stored.sha256_hex,
        }
    )
    return StoredInboundMedia(
        original=downloaded.media,
        media=media,
        data=downloaded.data,
        stored=stored,
    )


async def download_and_store_event_media(
    event: InboundEvent,
    *,
    settings: Settings | None = None,
    downloader: MediaDownloader | None = None,
) -> tuple[InboundEvent, list[StoredInboundMedia]]:
    if not event.media:
        return event, []

    settings = settings or get_settings()
    active_downloader = downloader or downloader_for_event(event, settings)
    stored_items: list[StoredInboundMedia] = []
    for media in event.media:
        downloaded = await active_downloader.download(media)
        stored_items.append(store_downloaded_media(event, downloaded, settings=settings))

    stored_media = [item.media for item in stored_items]
    return event.model_copy(update={"media": stored_media}), stored_items
