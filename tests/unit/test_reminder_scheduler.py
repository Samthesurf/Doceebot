"""Tests for the daily work-log reminder scheduler (standalone service)."""

from __future__ import annotations

import time
from datetime import datetime
from types import SimpleNamespace
from typing import Any

from whatsapp_ai_agent.db.models import ConversationSession, ReminderState
from whatsapp_ai_agent.notifications import reminder_messages
from whatsapp_ai_agent.notifications.reminder_scheduler import (
    ReminderScheduler,
    WeeklyReportScheduler,
    compute_next_fire,
    compute_next_weekly_fire,
)


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
        ReminderScheduler._format_twilio_to("whatsapp:+234****5678")
        == "whatsapp:+234****5678"
    )
    assert (
        ReminderScheduler._format_twilio_to("+234****5678") == "whatsapp:+234****5678"
    )


def test_compute_next_fire_rolls_to_tomorrow_after_time_passed() -> None:
    from zoneinfo import ZoneInfo

    tz = ZoneInfo("Africa/Lagos")
    now = datetime(2026, 7, 15, 18, 0, tzinfo=tz)
    fire = compute_next_fire(now, 17, 30, weekdays_only=False)
    assert fire.date().isoformat() == "2026-07-16"
    assert (fire.hour, fire.minute) == (17, 30)


def test_compute_next_fire_rolls_weekend_to_monday() -> None:
    from zoneinfo import ZoneInfo

    tz = ZoneInfo("Africa/Lagos")
    sat = datetime(2026, 7, 18, 17, 30, tzinfo=tz)
    assert sat.weekday() == 5
    fire = compute_next_fire(sat, 17, 30, weekdays_only=True)
    assert fire.weekday() == 0
    assert fire.date().isoformat() == "2026-07-20"

    sun = datetime(2026, 7, 19, 17, 30, tzinfo=tz)
    assert sun.weekday() == 6
    assert compute_next_fire(sun, 17, 30, weekdays_only=True).date().isoformat() == "2026-07-20"

    fri = datetime(2026, 7, 17, 10, 0, tzinfo=tz)
    assert fri.weekday() == 4
    assert compute_next_fire(fri, 17, 30, weekdays_only=True) == datetime(
        2026, 7, 17, 17, 30, tzinfo=tz
    )

    # Friday 18:00 (after the fire time) -> rolls forward to Monday.
    fri_late = datetime(2026, 7, 17, 18, 0, tzinfo=tz)
    next_fire = compute_next_fire(fri_late, 17, 30, weekdays_only=True)
    assert next_fire.date().isoformat() == "2026-07-20"


class _FakeSession:
    """In-memory stand-in for a SQLAlchemy session used by the claim logic."""

    def __init__(self, rows: list[ReminderState] | None = None) -> None:
        self._rows = {row.name: row for row in (rows or [])}
        self.committed = False
        self.added: list[Any] = []

    def execute(self, stmt):  # noqa: ANN001
        rows = list(self._rows.values())
        return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: rows))

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

    original = mod.get_session_factory
    mod.get_session_factory = _FakeFactory(session)  # type: ignore[assignment]
    try:
        idx1 = scheduler._claim_dispatch()
        assert idx1 == 0
        assert session.committed is True
        fired = session._rows[mod._STATE_LAST_FIRED_DATE]
        assert fired.text_value is not None

        idx2 = scheduler._claim_dispatch()
        assert idx2 is None

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
    rows = [
        ConversationSession(platform="telegram", platform_chat_id="111", status="active"),
        ConversationSession(platform="telegram", platform_chat_id="111", status="active"),
        ConversationSession(
            platform="whatsapp_twilio", platform_chat_id="whatsapp:+1", status="active"
        ),
        ConversationSession(platform="telegram", platform_chat_id="222", status="closed"),
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


def test_dispatch_sends_rotated_message_once_per_day() -> None:
    settings = SimpleNamespace(
        reminder_timezone="UTC",
        reminder_time_hour=17,
        reminder_time_minute=30,
    )
    sent: list[tuple[str, str, str]] = []

    scheduler = ReminderScheduler(settings=settings)
    scheduler.settings = settings  # type: ignore[attr-defined]

    # Claim the day once (index 0), then simulate "already fired today".
    state = {"claimed": False}

    def fake_claim() -> int | None:
        if state["claimed"]:
            return None
        state["claimed"] = True
        return 0

    def fake_recipients(s: object) -> list[tuple[str, str]]:
        return [("telegram", "111"), ("whatsapp_twilio", "whatsapp:+1")]

    def fake_send(s, platform, chat_id, message):  # noqa: ANN001
        sent.append((platform, chat_id, message))

    scheduler._claim_dispatch = fake_claim  # type: ignore[assignment]
    scheduler._load_recipients = fake_recipients  # type: ignore[assignment]
    scheduler._send_one_sync = fake_send  # type: ignore[assignment]

    scheduler._dispatch()
    scheduler._dispatch()  # second call same day must be suppressed

    # Day 1: both recipients get the (single, rotated) message once each.
    assert len(sent) == 2
    # Day 2 (would be a re-run): suppressed, no extra sends.
    assert all(
        m == reminder_messages.REMINDER_MESSAGES[0] for _, _, m in sent
    )
    platforms = {(p, c) for p, c, _ in sent}
    assert platforms == {("telegram", "111"), ("whatsapp_twilio", "whatsapp:+1")}


def test_run_forever_exits_on_interrupt(monkeypatch) -> None:
    settings = SimpleNamespace(
        reminder_timezone="UTC",
        reminder_time_hour=17,
        reminder_time_minute=30,
        reminder_weekdays_only=True,
    )
    scheduler = ReminderScheduler(settings=settings)

    sleeps: list[float] = []

    def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        raise KeyboardInterrupt()

    monkeypatch.setattr(time, "sleep", fake_sleep)
    # Let _sleep_until_next_fire run for real so it calls time.sleep (which we
    # patched to abort the loop), and stub the delivery so nothing is sent.
    monkeypatch.setattr(scheduler, "_dispatch", lambda: None)

    try:
        scheduler.run_forever()
    except KeyboardInterrupt:
        pass
    assert sleeps


def test_compute_next_weekly_fire_targets_friday_at_five() -> None:
    from zoneinfo import ZoneInfo

    tz = ZoneInfo("Africa/Lagos")
    wednesday = datetime(2026, 7, 15, 12, 0, tzinfo=tz)
    assert compute_next_weekly_fire(wednesday, 17, 0) == datetime(
        2026, 7, 17, 17, 0, tzinfo=tz
    )

    friday_before = datetime(2026, 7, 17, 16, 59, tzinfo=tz)
    assert compute_next_weekly_fire(friday_before, 17, 0).date().isoformat() == "2026-07-17"

    friday_after = datetime(2026, 7, 17, 17, 1, tzinfo=tz)
    assert compute_next_weekly_fire(friday_after, 17, 0).date().isoformat() == "2026-07-24"


def test_weekly_scheduler_uses_configured_friday_time() -> None:
    settings = SimpleNamespace(
        weekly_report_timezone="UTC",
        weekly_report_time_hour=17,
        weekly_report_time_minute=0,
    )
    scheduler = WeeklyReportScheduler(settings=settings)
    assert scheduler._hour == 17
    assert scheduler._minute == 0
    assert scheduler._tz is not None
