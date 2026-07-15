"""Daily work-log reminder scheduler for Doceebot.

Doceebot runs as a plain FastAPI service (no Celery worker or beat is
deployed). Rather than coupling the reminder loop to the API workers, the
scheduler runs as its own dedicated systemd service
(``doceebot-reminder.service``) that launches
``python -m whatsapp_ai_agent.notifications.run_scheduler``. That keeps the
broadcast independent of API restarts and avoids the multi worker duplication
problem entirely: there is exactly one scheduler process.

The loop sleeps until the configured local fire time, then broadcasts one
reminder message to every active conversation recipient. The message is
rotated through ``REMINDER_MESSAGES`` so the daily ping never goes stale.

The rotation index is persisted in the ``reminder_state`` table and the daily
dispatch is claimed under a database row lock (``last_fired_date``), so even
if the process is restarted it will never send twice on the same calendar day.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from whatsapp_ai_agent.config import Settings, get_settings
from whatsapp_ai_agent.db.models import ConversationSession, ReminderState
from whatsapp_ai_agent.db.session import get_session_factory
from whatsapp_ai_agent.integrations.telegram.sender import TelegramSender
from whatsapp_ai_agent.integrations.whatsapp_meta.sender import MetaWhatsAppSender
from whatsapp_ai_agent.integrations.whatsapp_twilio.sender import TwilioWhatsAppSender
from whatsapp_ai_agent.notifications.reminder_messages import reminder_at, reminder_count

logger = logging.getLogger(__name__)

_STATE_LAST_INDEX = "last_index"
_STATE_LAST_FIRED_DATE = "last_fired_date"

# Refresh the sleep loop in small steps so a stopped process exits promptly
# even when the next fire is many hours away.
_POLL_STEP_SECONDS = 30.0


def compute_next_fire(
    now: datetime, hour: int, minute: int, weekdays_only: bool
) -> datetime:
    """Return the next local fire time at ``hour:minute``.

    If that time has already passed today, roll forward a day. When
    ``weekdays_only`` is set, weekend fire times roll forward to the following
    Monday.
    """

    fire = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if fire <= now:
        fire += timedelta(days=1)
    if weekdays_only:
        fire = _roll_to_weekday(fire)
    return fire


def _roll_to_weekday(candidate: datetime) -> datetime:
    """Roll ``candidate`` forward to the next Monday through Friday.

    ``datetime.weekday()`` returns 5 for Saturday and 6 for Sunday, so any
    value at or above 5 is pushed to the following weekday. At most three days
    of roll-forward are ever needed (Sat -> Mon).
    """

    while candidate.weekday() >= 5:
        candidate += timedelta(days=1)
    return candidate


class ReminderScheduler:
    """Runs the once daily reminder broadcast."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._tz = self._resolve_timezone(self.settings.reminder_timezone)
        self._hour = self.settings.reminder_time_hour
        self._minute = self.settings.reminder_time_minute

    @staticmethod
    def _resolve_timezone(name: str):
        try:
            from zoneinfo import ZoneInfo

            return ZoneInfo(name)
        except Exception:  # noqa: BLE001 - fall back to UTC if tz unknown
            logger.warning("unknown reminder timezone %r; using UTC", name)
            return UTC

    def run_forever(self) -> None:
        """Blocking entry point for the dedicated systemd service."""

        logger.info(
            "reminder scheduler started (fires daily at %02d:%02d %s, "
            "weekdays_only=%s)",
            self._hour,
            self._minute,
            self.settings.reminder_timezone,
            self.settings.reminder_weekdays_only,
        )
        while True:
            try:
                self._sleep_until_next_fire()
                self._dispatch()
            except Exception:  # noqa: BLE001 - never tight-loop on a bad tick
                logger.exception(
                    "reminder scheduler tick failed; rescheduling in %.0fs",
                    _POLL_STEP_SECONDS,
                )
                time.sleep(_POLL_STEP_SECONDS)

    def _sleep_until_next_fire(self) -> None:
        now = datetime.now(self._tz)
        fire_time = compute_next_fire(
            now, self._hour, self._minute, self.settings.reminder_weekdays_only
        )
        wait = (fire_time - now).total_seconds()
        logger.info(
            "next work-log reminder in %.0fs (at %s %s)",
            wait,
            fire_time.strftime("%Y-%m-%d %H:%M"),
            self.settings.reminder_timezone,
        )
        while wait > 0:
            step = min(wait, _POLL_STEP_SECONDS)
            time.sleep(step)
            wait -= step

    def _dispatch(self) -> None:
        index = self._claim_dispatch()
        if index is None:
            # Already fired today (or a restart landed after the lock was set).
            return

        settings = get_settings()
        recipients = self._load_recipients(settings)
        if not recipients:
            logger.info("no active conversation recipients for today's reminder")
            return

        message = reminder_at(index)
        logger.info(
            "sending work-log reminder #%d to %d recipient(s)",
            index,
            len(recipients),
        )
        for platform, chat_id in recipients:
            try:
                self._send_one_sync(settings, platform, chat_id, message)
            except Exception:  # noqa: BLE001 - one bad recipient must not stop the rest
                logger.warning(
                    "failed to send reminder to %s chat %s",
                    platform,
                    chat_id,
                    exc_info=True,
                )

    def _claim_dispatch(self) -> int | None:
        """Atomically claim today's dispatch and return the rotation index.

        Returns ``None`` if another run already fired today.
        """

        factory = get_session_factory(self.settings)
        count = reminder_count()
        today = datetime.now(self._tz).strftime("%Y-%m-%d")
        with factory() as db:
            rows = (
                db.execute(
                    select(ReminderState)
                    .where(
                        ReminderState.name.in_(
                            [_STATE_LAST_INDEX, _STATE_LAST_FIRED_DATE]
                        )
                    )
                    .with_for_update()
                )
                .scalars()
                .all()
            )
            state = {row.name: row for row in rows}

            fired_row = state.get(_STATE_LAST_FIRED_DATE)
            if fired_row is not None and fired_row.text_value == today:
                return None

            index_row = state.get(_STATE_LAST_INDEX)
            if index_row is None:
                index_row = ReminderState(name=_STATE_LAST_INDEX, int_value=0)
                db.add(index_row)
            if fired_row is None:
                fired_row = ReminderState(name=_STATE_LAST_FIRED_DATE, text_value="")
                db.add(fired_row)
            db.flush()

            next_index = index_row.int_value % count
            index_row.int_value = next_index + 1
            fired_row.text_value = today
            now_utc = datetime.now(UTC)
            index_row.updated_at = now_utc
            fired_row.updated_at = now_utc
            db.commit()
        return next_index

    def _load_recipients(self, settings: Settings) -> list[tuple[str, str]]:
        factory = get_session_factory(settings)
        with factory() as db:
            rows = (
                db.execute(
                    select(
                        ConversationSession.platform,
                        ConversationSession.platform_chat_id,
                    )
                    .where(
                        ConversationSession.status == "active",
                        ConversationSession.platform_chat_id.is_not(None),
                    )
                    .distinct()
                )
                .all()
            )
        return [(row.platform, row.platform_chat_id) for row in rows]

    def _send_one_sync(
        self, settings: Settings, platform: str, chat_id: str, message: str
    ) -> None:
        if platform == "telegram":
            sender = TelegramSender(settings=settings)
            asyncio.run(sender.send_text(chat_id=chat_id, text=message))
        elif platform == "whatsapp_twilio":
            sender = TwilioWhatsAppSender(settings=settings)
            sender.send_text(to=self._format_twilio_to(chat_id), body=message)
        elif platform == "whatsapp_meta":
            sender = MetaWhatsAppSender(settings=settings)
            asyncio.run(sender.send_text(to=chat_id, body=message))
        else:
            logger.warning("skipping reminder for unknown platform %r", platform)

    @staticmethod
    def _format_twilio_to(chat_id: str) -> str:
        return chat_id if chat_id.startswith("whatsapp:") else f"whatsapp:{chat_id}"


def run_reminder_scheduler() -> ReminderScheduler | None:
    """Build the scheduler if enabled, else return ``None``.

    Used by the dedicated service entry point: when reminders are disabled the
    process simply exits (and systemd's ``Restart=on-failure`` leaves it
    stopped rather than looping).
    """

    settings = get_settings()
    if not settings.reminder_enabled:
        logger.info("daily work-log reminder disabled (REMINDER_ENABLED is not true)")
        return None
    return ReminderScheduler(settings=settings)
