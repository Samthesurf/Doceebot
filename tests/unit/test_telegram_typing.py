import asyncio

import pytest

from whatsapp_ai_agent.config import Settings
from whatsapp_ai_agent.integrations.telegram.sender import TelegramSender


class FakeBot:
    """Records chat-action calls and never touches the Telegram network."""

    def __init__(self) -> None:
        self.chat_actions: list[str] = []
        self.sent_messages: list[str] = []

    async def send_chat_action(self, *, chat_id: object, action: str) -> None:
        self.chat_actions.append(action)

    async def send_message(self, *, chat_id: object, text: str) -> None:
        self.sent_messages.append(text)


def _make_sender() -> tuple[TelegramSender, FakeBot]:
    bot = FakeBot()
    # Inject a fake bot so TelegramSender never builds a real telegram.Bot
    # (which requires TELEGRAM_BOT_TOKEN). The structural FakeBot satisfies the
    # runtime calls send_typing / send_text make.
    sender = TelegramSender(bot=bot, settings=Settings(_env_file=None))  # type: ignore[arg-type]
    return sender, bot


@pytest.mark.asyncio
async def test_send_typing_emits_single_chat_action():
    sender, bot = _make_sender()
    await sender.send_typing(chat_id="5124334968")
    assert bot.chat_actions == ["typing"]


@pytest.mark.asyncio
async def test_typing_context_manager_refreshes_until_block_exits():
    sender, bot = _make_sender()

    async def slow_work() -> None:
        # Simulate a long AI turn longer than Telegram's ~5s typing expiry.
        await asyncio.sleep(9.0)

    indicator = sender.typing(chat_id="5124334968")
    async with indicator:
        await slow_work()

    # 9s block with a 4s refresh interval -> multiple refreshes, not a single one.
    assert bot.chat_actions.count("typing") >= 3
    # The background loop task is fully stopped after the block exits.
    assert indicator._task is None


@pytest.mark.asyncio
async def test_typing_context_manager_stops_on_exception():
    sender, bot = _make_sender()

    indicator = sender.typing(chat_id="5124334968")
    with pytest.raises(ValueError):
        async with indicator:
            raise ValueError("boom")

    # Indicator was started, then the loop was cancelled cleanly.
    assert bot.chat_actions.count("typing") >= 1
    assert indicator._task is None
