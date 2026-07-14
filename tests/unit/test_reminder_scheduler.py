"""Tests for the daily work-log reminder scheduler."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from whatsapp_ai_agent.db.models import ConversationSession, ReminderState
from whatsapp_ai_agent.notifications import reminder_messages
from whatsapp_ai_agent.notifications.reminder_scheduler import ReminderScheduler


def test_twenty_messages_configured() -> None:
    assert reminder_messages.reminder_count() == 20
    assert len(reminder_messages.REMINDER_MESSAGES) == 20


def test_reminder_rotation_wraps() -> None:
    count = reminder_messages.reminder_count()
    assert reminder_messages.reminder_at(0) == reminder_messages.REMINDER_MESSAGES[0]
    assert reminder_messages.reminder_at(count) == reminder_messages.REMINDER_MESSAGES[0]
    assert reminder_messages.reminder_at(count + 1) == reminder_messages.REMINDER_MESSAGES[1]


def test_format_twilio_to_preserves_prefix() -> None:
    assert (
        ReminderScheduler._format_twilio_to("whatsapp:+2348012345678")
        == "whatsapp:+2348012345678"
    )
    assert (
        ReminderScheduler._format_twilio_to("+2348012345678") == "whatsapp:+2348012345678"
    )


class _FakeSession:
    """In-memory stand-in for a SQLAlchemy session used by the claim logic."""

    def __init__(self, rows: list[ReminderState] | None = None) -> None:
        self._rows = {row.name: row for row in (rows or [])}
        self.committed = False
        self.added: list[Any] = []

    def execute(self, stmt):  # noqa: ANN001 - only needs to satisfy .scalars().all()
        rows = list(self._rows.values())
        result = SimpleNamespace(
            scalars=lambda: SimpleNamespace(all=lambda: rows)
        )
        return result

    def add(self, obj: Any) -> None:
        self.added.append(obj)
        self._rows[obj.name] = obj

    def flush(self) -> None:
        return None

    def commit(self) -> None:
        self.committed = True

    def __enter__(self) -> _FakeSession:
        return self

    def __exit__(self, *exc: object) -> None:
        return None


class _FakeFactory:
    def __init__(self, session: _FakeSession) -> None:
        self._session = session

    def __call__(self, settings=None) -> _FakeSession:
        def _make() -> _FakeSession:
            return self._session

        return _make


def test_claim_returns_rotating_index_and_locks_day() -> None:
    settings = SimpleNamespace(
        reminder_timezone="UTC",
        reminder_time_hour=17,
        reminder_time_minute=30,
    )
    session = _FakeSession()
    scheduler = ReminderScheduler(settings=settings)
    scheduler.settings = settings  # type: ignore[attr-defined]
    import whatsapp_ai_agent.notifications.reminder_scheduler as mod

    # Patch the session factory used inside the claim.
    original = mod.get_session_factory
    mod.get_session_factory = _FakeFactory(session)  # type: ignore[assignment]
    try:
        # First claim of the day: index 0, marks today fired.
        idx1 = scheduler._claim_dispatch()
        assert idx1 == 0
        assert session.committed is True
        fired = session._rows[mod._STATE_LAST_FIRED_DATE]
        assert fired.text_value is not None

        # A second claim the same day must be suppressed (returns None).
        idx2 = scheduler._claim_dispatch()
        assert idx2 is None

        # Simulate next day by clearing the fired date, index should advance.
        session._rows[mod._STATE_LAST_FIRED_DATE].text_value = "2000-01-01"
        idx3 = scheduler._claim_dispatch()
        assert idx3 == 1
    finally:
        mod.get_session_factory = original  # type: ignore[assignment]


def test_load_recipients_returns_distinct_active_chats() -> None:
    settings = SimpleNamespace(
        reminder_timezone="UTC",
        reminder_time_hour=17,
        reminder_time_minute=30,
    )
    session = _FakeSession()
    # Two distinct active chats plus a duplicate (same platform+chat) and a
    # closed session that must be excluded.
    session.added = []
    rows = [
        ConversationSession(
            platform="telegram", platform_chat_id="111", status="active"
        ),
        ConversationSession(
            platform="telegram", platform_chat_id="111", status="active"
        ),
        ConversationSession(
            platform="whatsapp_twilio", platform_chat_id="whatsapp:+1", status="active"
        ),
        ConversationSession(
            platform="telegram", platform_chat_id="222", status="closed"
        ),
    ]
    scheduler = ReminderScheduler(settings=settings)
    import whatsapp_ai_agent.notifications.reminder_scheduler as mod

    original = mod.get_session_factory

    class _RecipientFactory:
        def __call__(self, settings=None) -> Any:
            def _make() -> Any:
                class _S:
                    def execute(self, stmt):  # noqa: ANN001
                        seen: set[tuple[str, str]] = set()
                        result = []
                        for r in rows:
                            if getattr(r, "status", None) != "active":
                                continue
                            key = (r.platform, r.platform_chat_id)
                            if r.platform_chat_id is None or key in seen:
                                continue
                            seen.add(key)
                            result.append(
                                SimpleNamespace(
                                    platform=r.platform,
                                    platform_chat_id=r.platform_chat_id,
                                )
                            )
                        return SimpleNamespace(all=lambda: result)

                    def __enter__(self) -> _S:
                        return self

                    def __exit__(self, *exc: object) -> None:
                        return None

                return _S()

            return _make

    mod.get_session_factory = _RecipientFactory()  # type: ignore[assignment]
    try:
        recipients = scheduler._load_recipients(settings)  # type: ignore[arg-type]
    finally:
        mod.get_session_factory = original  # type: ignore[assignment]

    assert recipients == [
        ("telegram", "111"),
        ("whatsapp_twilio", "whatsapp:+1"),
    ]


def test_next_weekday_rolls_weekend_to_monday() -> None:
    from datetime import datetime

    scheduler = ReminderScheduler(
        settings=SimpleNamespace(
            reminder_timezone="UTC",
            reminder_time_hour=17,
            reminder_time_minute=30,
        )
    )

    # Friday 17:30 -> stays Friday.
    friday = datetime(2026, 7, 17, 17, 30)  # a Friday
    assert friday.weekday() == 4
    assert scheduler._next_weekday(friday) == friday

    # Saturday 17:30 -> Monday 17:30.
    saturday = datetime(2026, 7, 18, 17, 30)
    assert saturday.weekday() == 5
    rolled = scheduler._next_weekday(saturday)
    assert rolled.weekday() == 0  # Monday
    assert rolled.date().isoformat() == "2026-07-20"

    # Sunday 17:30 -> Monday 17:30.
    sunday = datetime(2026, 7, 19, 17, 30)
    assert sunday.weekday() == 6
    assert scheduler._next_weekday(sunday).date().isoformat() == "2026-07-20"
