from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from whatsapp_ai_agent.config import Settings, get_settings
from whatsapp_ai_agent.core.events import InboundEvent
from whatsapp_ai_agent.db.session import get_db_session
from whatsapp_ai_agent.integrations.telegram.parser import parse_telegram_update
from whatsapp_ai_agent.integrations.telegram.sender import TelegramSender
from whatsapp_ai_agent.llm.schemas import ChatParseResult
from whatsapp_ai_agent.memory.tenant_scope import TenantResolution, resolve_event_tenant_scope
from whatsapp_ai_agent.memory.work_logs import (
    build_confirmation_message,
    build_upload_processed_message,
)
from whatsapp_ai_agent.security.webhooks import validate_telegram_secret_header
from whatsapp_ai_agent.workflows.chat_processing import process_inbound_event

router = APIRouter(tags=["telegram"])


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


async def process_live_telegram_event(
    event: InboundEvent,
    *,
    settings: Settings,
    db_session: Session,
) -> str:
    resolution = resolve_event_tenant_scope(event, db_session)
    if not resolution.resolved:
        return build_unresolved_scope_message(event, resolution)

    result = await process_inbound_event(
        resolution.event,
        settings=settings,
        db_session=db_session,
        download_media=True,
        extract_media=_media_extraction_enabled(settings),
    )
    db_session.commit()
    return result.reply_text


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
    reply_text = await process_live_telegram_event(event, settings=settings, db_session=db_session)
    if event.platform_chat_id is not None:
        sender = TelegramSender(settings=settings)
        await sender.send_text(chat_id=event.platform_chat_id, text=reply_text)
    return {"status": "accepted"}
