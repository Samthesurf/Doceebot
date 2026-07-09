import asyncio
from types import SimpleNamespace

import pytest

from whatsapp_ai_agent.config import Settings
from whatsapp_ai_agent.integrations.telegram.sender import TelegramSender


class FakeBot:
    """Records chat-action calls and never touches the Telegram network."""

    def __init__(self) -> None:
        self.chat_actions: list[str] = []
        self.sent_messages: list[str] = []
        self.edited_messages: list[str] = []

    async def send_chat_action(self, *, chat_id: object, action: str) -> None:
        self.chat_actions.append(action)

    async def send_message(self, *, chat_id: object, text: str) -> object:
        self.sent_messages.append(text)
        return SimpleNamespace(message_id=len(self.sent_messages))

    async def edit_message_text(self, *, chat_id: object, message_id: object, text: str) -> None:
        self.edited_messages.append(text)


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


@pytest.mark.asyncio
async def test_stream_text_reveals_progressively_then_full():
    sender, bot = _make_sender()

    # Short chat + small chunk so the test runs quickly.
    await sender.stream_text(
        chat_id="5124334968",
        text="Logged: site visit. Missing: supervisor sign-off.",
        chunk_size=8,
        delay_seconds=0,
    )

    # First an initial message, then edits that grow toward the full text.
    assert bot.sent_messages == ["Logged: "]
    assert bot.edited_messages[0] == "Logged: site vis"
    assert bot.edited_messages[-1] == "Logged: site visit. Missing: supervisor sign-off."


@pytest.mark.asyncio
async def test_stream_text_swallows_edit_failure_and_shows_full():
    sender, bot = _make_sender()

    async def boom(*, chat_id, message_id, text):
        raise RuntimeError("edit blocked")

    bot.edit_message_text = boom  # type: ignore[assignment]

    await sender.stream_text(
        chat_id="5124334968",
        text="Final reply text",
        chunk_size=8,
        delay_seconds=0,
    )

    # Initial message sent; the failed edit is swallowed (no exception escapes)
    # and the cleanup edit also failed here, so nothing extra is recorded.
    assert bot.sent_messages == ["Final re"]
    assert bot.edited_messages == []


@pytest.mark.asyncio
async def test_stream_text_restores_full_text_on_edit_failure():
    sender, bot = _make_sender()
    calls = {"n": 0}

    async def flaky(*, chat_id, message_id, text):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("transient edit failure")
        bot.edited_messages.append(text)

    bot.edit_message_text = flaky  # type: ignore[assignment]

    await sender.stream_text(
        chat_id="5124334968",
        text="Final reply text",
        chunk_size=8,
        delay_seconds=0,
    )

    # First edit failed (transient), cleanup succeeded and restored full text.
    assert bot.sent_messages == ["Final re"]
    assert bot.edited_messages == ["Final reply text"]
