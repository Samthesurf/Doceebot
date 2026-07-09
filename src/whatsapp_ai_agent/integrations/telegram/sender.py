import asyncio
from logging import getLogger

from telegram import Bot

from whatsapp_ai_agent.config import Settings, get_settings
from whatsapp_ai_agent.integrations.telegram.client import build_telegram_bot

logger = getLogger(__name__)


class TelegramSender:
    def __init__(self, bot: Bot | None = None, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.bot = bot or build_telegram_bot(self.settings)

    async def send_text(self, *, chat_id: str | int, text: str) -> None:
        await self.bot.send_message(chat_id=chat_id, text=text)

    async def send_typing(self, *, chat_id: str | int) -> None:
        """Send a single 'typing…' chat action.

        Telegram expires this indicator after roughly five seconds, so for a
        long-running reply callers should use ``typing()`` instead, which keeps
        the indicator alive for the whole turn.
        """
        await self.bot.send_chat_action(chat_id=chat_id, action="typing")

    def typing(self, *, chat_id: str | int) -> "_TypingIndicator":
        """Return an async context manager that shows a live 'typing…' indicator.

        Usage::

            async with sender.typing(chat_id=chat_id):
                reply = await process_inbound_event(...)

        The native Telegram typing bubble is refreshed on an interval so it does
        not disappear while the bot is still working on a slow (10 to 15 second)
        reply.
        """
        return _TypingIndicator(self, chat_id)


class _TypingIndicator:
    """Loops Telegram ``send_chat_action`` typing actions until the block exits.

    Telegram's typing state auto-expires after about five seconds, so we send it
    repeatedly on a short interval. The loop stops as soon as the enclosing
    ``async with`` block completes (or raises), and any send error is logged
    rather than propagated so it never masks the real reply.
    """

    # Refresh a little under Telegram's ~5s expiry so the dots never blink off.
    _REFRESH_INTERVAL_SECONDS = 4.0

    def __init__(self, sender: TelegramSender, chat_id: str | int) -> None:
        self._sender = sender
        self._chat_id = chat_id
        self._task: asyncio.Task[None] | None = None

    async def _loop(self) -> None:
        while True:
            try:
                await self._sender.send_typing(chat_id=self._chat_id)
            except Exception:  # noqa: BLE001 - typing must never break the reply
                logger.warning("Telegram typing indicator refresh failed", exc_info=True)
            await asyncio.sleep(self._REFRESH_INTERVAL_SECONDS)

    async def __aenter__(self) -> "_TypingIndicator":
        # Show the bubble immediately, then keep it alive on a refresh loop.
        # Any failure to send must not break the reply, so swallow it here too.
        try:
            await self._sender.send_typing(chat_id=self._chat_id)
        except Exception:  # noqa: BLE001 - typing must never break the reply
            logger.warning("Telegram typing indicator failed on entry", exc_info=True)
        self._task = asyncio.create_task(self._loop())
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
