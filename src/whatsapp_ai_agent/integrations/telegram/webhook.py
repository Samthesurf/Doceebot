from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status

from whatsapp_ai_agent.config import Settings, get_settings
from whatsapp_ai_agent.core.events import InboundEvent
from whatsapp_ai_agent.integrations.telegram.parser import parse_telegram_update
from whatsapp_ai_agent.integrations.telegram.sender import TelegramSender
from whatsapp_ai_agent.security.webhooks import validate_telegram_secret_header

router = APIRouter(tags=["telegram"])


def build_acknowledgement(event: InboundEvent) -> str:
    if event.message_type == "text" and event.text:
        return "Received your work update. I have parsed it and the AI logging step is next."
    return (
        f"Received your {event.message_type} update. "
        "I have parsed it and the AI logging step is next."
    )


async def acknowledge_telegram_event(event: InboundEvent, settings: Settings) -> None:
    if event.platform_chat_id is None:
        return
    sender = TelegramSender(settings=settings)
    await sender.send_text(chat_id=event.platform_chat_id, text=build_acknowledgement(event))


@router.post("/telegram/webhook")
async def receive_telegram_update(
    update: dict[str, Any],
    request: Request,
    settings: Settings = Depends(get_settings),
) -> dict[str, str]:
    header = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if not validate_telegram_secret_header(header_value=header, settings=settings):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid Telegram secret")

    event = parse_telegram_update(update, timezone_name=settings.app_timezone)
    request.app.state.last_telegram_event = event
    await acknowledge_telegram_event(event, settings)
    return {"status": "accepted"}
