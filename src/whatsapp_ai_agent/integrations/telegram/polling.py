from telegram.ext import Application

from whatsapp_ai_agent.config import Settings, get_settings


def build_polling_application(settings: Settings | None = None) -> Application:
    settings = settings or get_settings()
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not configured")
    return Application.builder().token(settings.telegram_bot_token).build()
