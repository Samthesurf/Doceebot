from dataclasses import dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Protocol

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from whatsapp_ai_agent.config import Settings, get_settings
from whatsapp_ai_agent.core.events import InboundEvent
from whatsapp_ai_agent.db.session import get_db_session
from whatsapp_ai_agent.documents.schemas import DocumentAutomationResult, ManagedDocumentSummary
from whatsapp_ai_agent.integrations.telegram.parser import parse_telegram_update
from whatsapp_ai_agent.integrations.telegram.sender import TelegramSender
from whatsapp_ai_agent.llm.schemas import ChatParseResult
from whatsapp_ai_agent.media.storage import LocalStorage, get_media_storage
from whatsapp_ai_agent.memory.tenant_scope import TenantResolution, resolve_event_tenant_scope
from whatsapp_ai_agent.memory.work_logs import (
    build_confirmation_message,
    build_upload_processed_message,
)
from whatsapp_ai_agent.security.webhooks import validate_telegram_secret_header
from whatsapp_ai_agent.workflows.chat_processing import process_inbound_event

router = APIRouter(tags=["telegram"])


class TelegramDocumentSender(Protocol):
    async def send_document(
        self,
        *,
        chat_id: str | int,
        path: str | Path,
        caption: str | None = None,
    ) -> None: ...


@dataclass(frozen=True)
class TelegramProcessingOutcome:
    reply_text: str
    document_results: list[DocumentAutomationResult] = field(default_factory=list)


def build_acknowledgement(event: InboundEvent, parse_result: ChatParseResult | None = None) -> str:
    if parse_result is not None:
        if event.media:
            filename = next((media.filename for media in event.media if media.filename), None)
            return build_upload_processed_message(filename=filename, parse_result=parse_result)
        return build_confirmation_message(parse_result)

    if event.media:
        kind = event.message_type if event.message_type != "unknown" else "file"
        return (
            f"I received your {kind} upload. I will extract the useful work details, "
            "save it as a draft log, then ask only the missing follow-up questions."
        )
    if event.message_type == "location":
        return (
            "I received the location pin. I will attach it to the next work log "
            "that needs a site."
        )
    if event.message_type == "text" and event.text:
        return (
            "I received your work update. I will turn it into a draft log "
            "and ask for any missing details."
        )
    return "I received this update. I will parse it and ask for any missing details."


async def acknowledge_telegram_event(event: InboundEvent, settings: Settings) -> None:
    if event.platform_chat_id is None:
        return
    sender = TelegramSender(settings=settings)
    await sender.send_text(chat_id=event.platform_chat_id, text=build_acknowledgement(event))


def build_unresolved_scope_message(event: InboundEvent, resolution: TenantResolution) -> str:
    base = build_acknowledgement(event)
    return (
        f"{base}\n\n"
        "I cannot store or process the upload yet because this sender is not linked "
        f"to one organization ({resolution.reason}). Please link the account first."
    )


def _media_extraction_enabled(settings: Settings) -> bool:
    return bool(settings.gemini_api_key and settings.gemini_api_key != "change-me")


def build_document_delivery_caption(result: DocumentAutomationResult) -> str:
    verb = "created" if result.action == "created" else "updated"
    lines = [
        f"Edited file: {result.document.filename}",
        f"Status: {verb}; {result.rows_applied} row(s) applied.",
    ]
    if result.changes:
        lines.append("Changes:")
        lines.extend(f"- {change}" for change in result.changes[:4])
    lines.append("Open this attachment to see the actual edited document.")
    caption = "\n".join(lines)
    if len(caption) > 1024:
        return caption[:1000].rstrip() + "…"
    return caption


def _local_document_path(document: ManagedDocumentSummary, settings: Settings) -> Path | None:
    if document.storage_backend != "local" or not document.storage_key:
        return None
    path = LocalStorage(settings).path_for(document.storage_key)
    return path if path.exists() else None


async def send_document_result_file(
    *,
    sender: TelegramDocumentSender,
    chat_id: str | int,
    result: DocumentAutomationResult,
    settings: Settings,
) -> None:
    document = result.document
    if result.action not in {"created", "updated"} or not document.storage_key:
        return

    caption = build_document_delivery_caption(result)
    local_path = _local_document_path(document, settings)
    if local_path is not None:
        await sender.send_document(chat_id=chat_id, path=local_path, caption=caption)
        return

    storage = get_media_storage(settings)
    if not hasattr(storage, "read_bytes"):
        return
    with TemporaryDirectory() as tmp_dir:
        temp_path = Path(tmp_dir) / document.filename
        temp_path.write_bytes(storage.read_bytes(document.storage_key))  # type: ignore[union-attr]
        await sender.send_document(chat_id=chat_id, path=temp_path, caption=caption)


async def send_document_result_files(
    *,
    sender: TelegramDocumentSender,
    chat_id: str | int,
    results: list[DocumentAutomationResult],
    settings: Settings,
) -> None:
    for result in results:
        await send_document_result_file(
            sender=sender,
            chat_id=chat_id,
            result=result,
            settings=settings,
        )


async def process_live_telegram_event_result(
    event: InboundEvent,
    *,
    settings: Settings,
    db_session: Session,
) -> TelegramProcessingOutcome:
    resolution = resolve_event_tenant_scope(event, db_session)
    if not resolution.resolved:
        return TelegramProcessingOutcome(
            reply_text=build_unresolved_scope_message(event, resolution)
        )

    result = await process_inbound_event(
        resolution.event,
        settings=settings,
        db_session=db_session,
        download_media=True,
        extract_media=_media_extraction_enabled(settings),
    )
    db_session.commit()
    return TelegramProcessingOutcome(
        reply_text=result.reply_text,
        document_results=result.document_results,
    )


async def process_live_telegram_event(
    event: InboundEvent,
    *,
    settings: Settings,
    db_session: Session,
) -> str:
    outcome = await process_live_telegram_event_result(
        event,
        settings=settings,
        db_session=db_session,
    )
    return outcome.reply_text


@router.post("/telegram/webhook")
async def receive_telegram_update(
    update: dict[str, Any],
    request: Request,
    settings: Settings = Depends(get_settings),
    db_session: Session = Depends(get_db_session),
) -> dict[str, str]:
    header = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if not validate_telegram_secret_header(header_value=header, settings=settings):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid Telegram secret")

    event = parse_telegram_update(update, timezone_name=settings.app_timezone)
    request.app.state.last_telegram_event = event
    outcome = await process_live_telegram_event_result(
        event,
        settings=settings,
        db_session=db_session,
    )
    if event.platform_chat_id is not None:
        sender = TelegramSender(settings=settings)
        await sender.send_text(chat_id=event.platform_chat_id, text=outcome.reply_text)
        await send_document_result_files(
            sender=sender,
            chat_id=event.platform_chat_id,
            results=outcome.document_results,
            settings=settings,
        )
    return {"status": "accepted"}
