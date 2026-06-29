from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status

from whatsapp_ai_agent.config import Settings, get_settings
from whatsapp_ai_agent.integrations.telegram.parser import parse_telegram_update
from whatsapp_ai_agent.security.webhooks import validate_telegram_secret_header

router = APIRouter(tags=["telegram"])


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
    return {"status": "accepted"}
