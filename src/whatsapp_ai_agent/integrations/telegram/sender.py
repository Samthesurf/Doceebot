from pathlib import Path

from telegram import Bot

from whatsapp_ai_agent.config import Settings, get_settings
from whatsapp_ai_agent.integrations.telegram.client import build_telegram_bot


class TelegramSender:
    def __init__(self, bot: Bot | None = None, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.bot = bot or build_telegram_bot(self.settings)

    async def send_text(self, *, chat_id: str | int, text: str) -> None:
        await self.bot.send_message(chat_id=chat_id, text=text)

    async def send_document(
        self,
        *,
        chat_id: str | int,
        path: str | Path,
        caption: str | None = None,
    ) -> None:
        with Path(path).open("rb") as handle:
            await self.bot.send_document(chat_id=chat_id, document=handle, caption=caption)
