"""Daily work-log reminder scheduler for Doceebot.

Doceebot runs as a plain FastAPI service (no Celery worker or beat is
deployed), so this module ships a self contained daily loop. A single daemon
thread owns its own asyncio event loop and sleeps until the configured local
fire time, then broadcasts one reminder message to every active conversation
recipient. The message is rotated through :data:`REMINDER_MESSAGES` so the
daily ping never goes stale.

Concurrency: the FastAPI service runs with multiple uvicorn workers, and each
worker starts its own scheduler thread via the app lifespan. To avoid every
worker delivering the same message, the dispatch claims the day under a
database row lock (``reminder_state.last_fired_date``), so only the first
worker to commit actually sends.
"""

from __future__ import annotations

import asyncio
import logging
import threading
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

# Refresh the typing style loop in small steps so stop() is responsive even
# when the next fire is many hours away.
_POLL_STEP_SECONDS = 30.0


class ReminderScheduler:
    """Runs the once daily reminder broadcast in a dedicated thread."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._tz = self._resolve_timezone(self.settings.reminder_timezone)
        self._hour = self.settings.reminder_time_hour
        self._minute = self.settings.reminder_time_minute
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @staticmethod
    def _resolve_timezone(name: str):
        try:
            from zoneinfo import ZoneInfo

            return ZoneInfo(name)
        except Exception:  # noqa: BLE001 - fall back to UTC if tz unknown
            logger.warning("unknown reminder timezone %r; using UTC", name)
            return UTC

    def start(self) -> None:
        """Spawn the scheduler thread. Idempotent."""

        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name="reminder-scheduler", daemon=True
        )
        self._thread.start()
        logger.info(
            "reminder scheduler started (fires daily at %02d:%02d %s)",
            self._hour,
            self._minute,
            self.settings.reminder_timezone,
        )

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._run_async())
        except Exception:  # noqa: BLE001 - a dead scheduler thread must not crash the app
            logger.exception("reminder scheduler thread exited unexpectedly")
        finally:
            loop.close()

    async def _run_async(self) -> None:
        while not self._stop.is_set():
            try:
                await self._sleep_until_next_fire()
                if self._stop.is_set():
                    break
                await self._dispatch()
            except asyncio.CancelledError:
                break
            except Exception:  # noqa: BLE001 - never tight-loop on a bad tick
                logger.exception("reminder scheduler tick failed")
                await asyncio.sleep(_POLL_STEP_SECONDS)

    async def _sleep_until_next_fire(self) -> None:
        now = datetime.now(self._tz)
        fire_time = now.replace(
            hour=self._hour, minute=self._minute, second=0, microsecond=0
        )
        if fire_time <= now:
            fire_time += timedelta(days=1)
        wait = (fire_time - now).total_seconds()
        logger.info(
            "next work-log reminder in %.0fs (at %s %s)",
            wait,
            fire_time.strftime("%Y-%m-%d %H:%M"),
            self.settings.reminder_timezone,
        )
        while wait > 0 and not self._stop.is_set():
            step = min(wait, _POLL_STEP_SECONDS)
            await asyncio.sleep(step)
            wait -= step

    async def _dispatch(self) -> None:
        index = self._claim_dispatch()
        if index is None:
            # Another worker already fired today.
            return

        settings = get_settings()
        recipients = self._load_recipients(settings)
        if not recipients:
            logger.info("no active conversation recipients for today's reminder")
            return

        message = reminder_at(index)
        logger.info(
            "sending work-log reminder #%d to %d recipient(s)", index, len(recipients)
        )
        for platform, chat_id in recipients:
            try:
                await self._send_one(settings, platform, chat_id, message)
            except Exception:  # noqa: BLE001 - one bad recipient must not stop the rest
                logger.warning(
                    "failed to send reminder to %s chat %s",
                    platform,
                    chat_id,
                    exc_info=True,
                )

    def _claim_dispatch(self) -> int | None:
        """Atomically claim today's dispatch and return the rotation index.

        Returns ``None`` if another worker already fired today.
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

    async def _send_one(
        self, settings: Settings, platform: str, chat_id: str, message: str
    ) -> None:
        if platform == "telegram":
            sender = TelegramSender(settings=settings)
            await sender.send_text(chat_id=chat_id, text=message)
        elif platform == "whatsapp_twilio":
            sender = TwilioWhatsAppSender(settings=settings)
            sender.send_text(to=self._format_twilio_to(chat_id), body=message)
        elif platform == "whatsapp_meta":
            sender = MetaWhatsAppSender(settings=settings)
            await sender.send_text(to=chat_id, body=message)
        else:
            logger.warning("skipping reminder for unknown platform %r", platform)

    @staticmethod
    def _format_twilio_to(chat_id: str) -> str:
        return chat_id if chat_id.startswith("whatsapp:") else f"whatsapp:{chat_id}"


def start_reminder_scheduler() -> ReminderScheduler | None:
    """Start the reminder scheduler if enabled, else return ``None``.

    Safe to call from the FastAPI lifespan: when reminders are disabled it
    does nothing, and a missing configuration raises nothing here so the app
    boots normally.
    """

    settings = get_settings()
    if not settings.reminder_enabled:
        logger.info("daily work-log reminder disabled (REMINDER_ENABLED is not true)")
        return None
    scheduler = ReminderScheduler(settings=settings)
    scheduler.start()
    return scheduler
