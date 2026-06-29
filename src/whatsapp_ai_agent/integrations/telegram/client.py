from telegram import Bot

from whatsapp_ai_agent.config import Settings, get_settings


def build_telegram_bot(settings: Settings | None = None) -> Bot:
    settings = settings or get_settings()
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not configured")
    return Bot(token=settings.telegram_bot_token)
