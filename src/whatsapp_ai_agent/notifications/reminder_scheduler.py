"""Standalone daily reminders and weekly DOCX report scheduler.

The scheduler runs in ``doceebot-reminder.service`` as one process, separate
from the FastAPI workers. It owns two jobs:

* the weekday 17:30 work-log nudge, rotated through twenty messages;
* the Friday 17:00 weekly DOCX report, generated from that user's confirmed
  work logs for Monday through Friday.

Both jobs use ``reminder_state`` for once-per-period claims, so a restart does
not accidentally send a duplicate report or reminder.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Protocol
from uuid import UUID

from sqlalchemy import select

from whatsapp_ai_agent.config import Settings, get_settings
from whatsapp_ai_agent.db.models import ConversationSession, ReminderState, WorkLogEntry
from whatsapp_ai_agent.db.session import get_session_factory
from whatsapp_ai_agent.documents.automation import register_generated_document_file
from whatsapp_ai_agent.documents.reports import GeneratedReportFile, generate_report_files
from whatsapp_ai_agent.integrations.telegram.sender import TelegramSender
from whatsapp_ai_agent.integrations.whatsapp_meta.sender import MetaWhatsAppSender
from whatsapp_ai_agent.integrations.whatsapp_twilio.sender import TwilioWhatsAppSender
from whatsapp_ai_agent.llm.schemas import ReportRequest
from whatsapp_ai_agent.memory.work_logs import work_log_from_db
from whatsapp_ai_agent.notifications.reminder_messages import reminder_at, reminder_count

logger = logging.getLogger(__name__)

_STATE_LAST_INDEX = "last_index"
_STATE_LAST_FIRED_DATE = "last_fired_date"
_STATE_LAST_WEEKLY_REPORT_DATE = "last_weekly_report_date"
_POLL_STEP_SECONDS = 30.0
_DOCX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class ScheduledJob(Protocol):
    def next_fire_at(self) -> datetime: ...

    def dispatch(self) -> None: ...


def compute_next_fire(
    now: datetime, hour: int, minute: int, weekdays_only: bool
) -> datetime:
    """Return the next local fire time at ``hour:minute``."""

    fire = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if fire <= now:
        fire += timedelta(days=1)
    if weekdays_only:
        fire = _roll_to_weekday(fire)
    return fire


def compute_next_weekly_fire(now: datetime, hour: int, minute: int) -> datetime:
    """Return the next Friday fire time at ``hour:minute`` in ``now``'s zone."""

    fire = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    days_until_friday = (4 - now.weekday()) % 7
    fire += timedelta(days=days_until_friday)
    if fire <= now:
        fire += timedelta(days=7)
    return fire


def _roll_to_weekday(candidate: datetime) -> datetime:
    while candidate.weekday() >= 5:
        candidate += timedelta(days=1)
    return candidate


def _resolve_timezone(name: str):
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo(name)
    except Exception:  # noqa: BLE001 - fall back to UTC if tz unknown
        logger.warning("unknown scheduler timezone %r; using UTC", name)
        return UTC


def _sleep_until(fire_time: datetime) -> None:
    now = datetime.now(fire_time.tzinfo or UTC)
    wait = (fire_time - now).total_seconds()
    while wait > 0:
        time.sleep(min(wait, _POLL_STEP_SECONDS))
        wait -= min(wait, _POLL_STEP_SECONDS)


class ReminderScheduler:
    """Runs the weekday work-log reminder broadcast."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._tz = _resolve_timezone(self.settings.reminder_timezone)
        self._hour = self.settings.reminder_time_hour
        self._minute = self.settings.reminder_time_minute

    def next_fire_at(self) -> datetime:
        now = datetime.now(self._tz)
        return compute_next_fire(
            now,
            self._hour,
            self._minute,
            self.settings.reminder_weekdays_only,
        )

    def run_forever(self) -> None:
        logger.info(
            "reminder scheduler started (fires daily at %02d:%02d %s, weekdays_only=%s)",
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
                logger.exception("reminder scheduler tick failed")
                time.sleep(_POLL_STEP_SECONDS)

    def _sleep_until_next_fire(self) -> None:
        fire_time = self.next_fire_at()
        wait = (fire_time - datetime.now(self._tz)).total_seconds()
        logger.info(
            "next work-log reminder in %.0fs (at %s %s)",
            wait,
            fire_time.strftime("%Y-%m-%d %H:%M"),
            self.settings.reminder_timezone,
        )
        _sleep_until(fire_time)

    def dispatch(self) -> None:
        self._dispatch()

    def _dispatch(self) -> None:
        index = self._claim_dispatch()
        if index is None:
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
                self._send_one_sync(settings, platform, chat_id, message)
            except Exception:  # noqa: BLE001 - one bad recipient must not stop the rest
                logger.warning(
                    "failed to send reminder to %s chat %s",
                    platform,
                    chat_id,
                    exc_info=True,
                )

    def _claim_dispatch(self) -> int | None:
        factory = get_session_factory(self.settings)
        count = reminder_count()
        today = datetime.now(self._tz).strftime("%Y-%m-%d")
        with factory() as db:
            rows = (
                db.execute(
                    select(ReminderState)
                    .where(
                        ReminderState.name.in_([_STATE_LAST_INDEX, _STATE_LAST_FIRED_DATE])
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

    @staticmethod
    def _load_recipients(settings: Settings) -> list[tuple[str, str]]:
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


@dataclass(frozen=True)
class WeeklyRecipient:
    org_id: UUID
    user_id: UUID
    platform: str
    chat_id: str


class WeeklyReportScheduler:
    """Generates and delivers the Friday DOCX work report."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._tz = _resolve_timezone(self.settings.weekly_report_timezone)
        self._hour = self.settings.weekly_report_time_hour
        self._minute = self.settings.weekly_report_time_minute

    def next_fire_at(self) -> datetime:
        now = datetime.now(self._tz)
        return compute_next_weekly_fire(now, self._hour, self._minute)

    def run_forever(self) -> None:
        logger.info(
            "weekly report scheduler started (fires Friday at %02d:%02d %s)",
            self._hour,
            self._minute,
            self.settings.weekly_report_timezone,
        )
        while True:
            try:
                self._sleep_until_next_fire()
                self._dispatch()
            except Exception:  # noqa: BLE001 - never tight-loop on a bad tick
                logger.exception("weekly report scheduler tick failed")
                time.sleep(_POLL_STEP_SECONDS)

    def _sleep_until_next_fire(self) -> None:
        fire_time = self.next_fire_at()
        wait = (fire_time - datetime.now(self._tz)).total_seconds()
        logger.info(
            "next weekly work report in %.0fs (at %s %s)",
            wait,
            fire_time.strftime("%Y-%m-%d %H:%M"),
            self.settings.weekly_report_timezone,
        )
        _sleep_until(fire_time)

    def dispatch(self) -> None:
        self._dispatch()

    def _dispatch(self) -> None:
        week_start, week_end = self._current_week()
        recipients = self._load_recipients(self.settings)
        if not recipients:
            logger.info("no active recipients for this week's report")
            return
        if self._already_claimed(week_end):
            logger.info("weekly report already claimed for %s", week_end)
            return

        grouped: dict[tuple[UUID, UUID], list[WeeklyRecipient]] = {}
        for recipient in recipients:
            grouped.setdefault((recipient.org_id, recipient.user_id), []).append(recipient)

        for (org_id, user_id), channels in grouped.items():
            try:
                report = self._build_report(
                    org_id=org_id,
                    user_id=user_id,
                    week_start=week_start,
                    week_end=week_end,
                )
                caption = self._caption(week_start, week_end, report)
                for channel in channels:
                    try:
                        self._send_report(channel, report, caption)
                    except Exception:  # noqa: BLE001 - continue with other channels/users
                        logger.warning(
                            "failed to send weekly report to %s chat %s",
                            channel.platform,
                            channel.chat_id,
                            exc_info=True,
                        )
            except Exception:  # noqa: BLE001 - one user's report must not stop the batch
                logger.warning(
                    "failed to build weekly report for org=%s user=%s",
                    org_id,
                    user_id,
                    exc_info=True,
                )
        self._claim_week(week_end)

    def _current_week(self) -> tuple[date, date]:
        today = datetime.now(self._tz).date()
        monday = today - timedelta(days=today.weekday())
        return monday, monday + timedelta(days=4)

    def _already_claimed(self, week_end: date) -> bool:
        factory = get_session_factory(self.settings)
        with factory() as db:
            row = db.scalar(
                select(ReminderState).where(
                    ReminderState.name == _STATE_LAST_WEEKLY_REPORT_DATE
                )
            )
            return row is not None and row.text_value == week_end.isoformat()

    def _claim_week(self, week_end: date) -> None:
        factory = get_session_factory(self.settings)
        with factory() as db:
            row = db.scalar(
                select(ReminderState)
                .where(ReminderState.name == _STATE_LAST_WEEKLY_REPORT_DATE)
                .with_for_update()
            )
            if row is None:
                row = ReminderState(name=_STATE_LAST_WEEKLY_REPORT_DATE)
                db.add(row)
            row.text_value = week_end.isoformat()
            row.updated_at = datetime.now(UTC)
            db.commit()

    def _load_recipients(self, settings: Settings) -> list[WeeklyRecipient]:
        factory = get_session_factory(settings)
        with factory() as db:
            rows = (
                db.execute(
                    select(
                        ConversationSession.org_id,
                        ConversationSession.user_id,
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
        return [
            WeeklyRecipient(
                org_id=row.org_id,
                user_id=row.user_id,
                platform=row.platform,
                chat_id=row.platform_chat_id,
            )
            for row in rows
        ]

    def _build_report(
        self,
        *,
        org_id: UUID,
        user_id: UUID,
        week_start: date,
        week_end: date,
    ) -> GeneratedReportFile:
        factory = get_session_factory(self.settings)
        with factory() as db:
            entries = list(
                db.scalars(
                    select(WorkLogEntry)
                    .where(
                        WorkLogEntry.org_id == org_id,
                        WorkLogEntry.user_id == user_id,
                        WorkLogEntry.work_date >= week_start,
                        WorkLogEntry.work_date <= week_end,
                        WorkLogEntry.confirmation_status == "confirmed",
                        WorkLogEntry.status != "cancelled",
                    )
                    .order_by(WorkLogEntry.work_date.asc(), WorkLogEntry.created_at.asc())
                )
            )
        work_logs = [work_log_from_db(entry) for entry in entries]
        title = f"Weekly Work Report, {week_start.isoformat()} to {week_end.isoformat()}"
        request = ReportRequest(
            report_type="weekly",
            title=title,
            start_date=week_start,
            end_date=week_end,
            output_format="docx",
        )
        output_dir = (
            Path(self.settings.local_storage_dir)
            / "weekly-reports"
            / str(org_id)
            / str(user_id)
        )
        use_llm = bool(self.settings.deepseek_api_key)
        try:
            generated = asyncio.run(
                generate_report_files(
                    org_id=str(org_id),
                    work_logs=work_logs,
                    output_dir=output_dir,
                    request=request,
                    formats={"docx"},
                    store=True,
                    use_llm=use_llm,
                    settings=self.settings,
                )
            )
        except Exception:
            logger.warning(
                "weekly report LLM generation failed; using deterministic fallback",
                exc_info=True,
            )
            generated = asyncio.run(
                generate_report_files(
                    org_id=str(org_id),
                    work_logs=work_logs,
                    output_dir=output_dir,
                    request=request,
                    formats={"docx"},
                    store=True,
                    use_llm=False,
                    settings=self.settings,
                )
            )
        report = next(file for file in generated if file.format == "docx")

        with get_session_factory(self.settings)() as db:
            register_generated_document_file(
                org_id=org_id,
                owner_user_id=user_id,
                path=report.path,
                stored=report.stored,
                db_session=db,
                display_name=title,
                summary=(
                    f"Weekly work report for {week_start.isoformat()} to {week_end.isoformat()}."
                ),
                settings=self.settings,
            )
            db.commit()
        logger.info(
            "built weekly report for org=%s user=%s (%d confirmed log(s))",
            org_id,
            user_id,
            len(work_logs),
        )
        return report

    @staticmethod
    def _caption(week_start: date, week_end: date, report: GeneratedReportFile) -> str:
        return (
            f"Your weekly work report is ready.\n"
            f"Week covered: {week_start.isoformat()} to {week_end.isoformat()}\n"
            "It is built from the work logs confirmed this week."
        )

    def _send_report(
        self,
        recipient: WeeklyRecipient,
        report: GeneratedReportFile,
        caption: str,
    ) -> None:
        if recipient.platform == "telegram":
            asyncio.run(self._send_telegram_report(recipient.chat_id, report.path, caption))
            return

        if report.stored is None or not report.stored.url:
            raise RuntimeError(
                f"{recipient.platform} report delivery needs a public storage URL; "
                "configure PUBLIC_MEDIA_BASE_URL or CLOUDFLARE_R2_PUBLIC_BASE_URL"
            )
        if recipient.platform == "whatsapp_twilio":
            sender = TwilioWhatsAppSender(settings=self.settings)
            sender.send_media(
                to=ReminderScheduler._format_twilio_to(recipient.chat_id),
                body=caption,
                media_urls=[report.stored.url],
            )
        elif recipient.platform == "whatsapp_meta":
            sender = MetaWhatsAppSender(settings=self.settings)
            # Prefer a public URL when storage provides one; otherwise upload the
            # locally-stored DOCX to Meta and deliver it by media id (no CDN needed).
            if report.stored is not None and report.stored.url:
                asyncio.run(
                    sender.send_document(
                        to=recipient.chat_id,
                        body=caption,
                        filename=report.path.name,
                        document_url=report.stored.url,
                    )
                )
            else:
                asyncio.run(
                    sender.send_document_file(
                        to=recipient.chat_id,
                        body=caption,
                        filename=report.path.name,
                        document_path=report.path,
                    )
                )
        else:
            logger.warning("skipping weekly report for unknown platform %r", recipient.platform)

    async def _send_telegram_report(self, chat_id: str, path: Path, caption: str) -> None:
        sender = TelegramSender(settings=self.settings)
        await sender.bot.send_document(chat_id=chat_id, document=path, caption=caption)


def run_reminder_scheduler() -> ReminderScheduler | None:
    settings = get_settings()
    if not settings.reminder_enabled:
        logger.info("daily work-log reminder disabled (REMINDER_ENABLED is not true)")
        return None
    return ReminderScheduler(settings=settings)


def run_weekly_report_scheduler() -> WeeklyReportScheduler | None:
    settings = get_settings()
    if not settings.weekly_report_enabled:
        logger.info("weekly report disabled (WEEKLY_REPORT_ENABLED is not true)")
        return None
    return WeeklyReportScheduler(settings=settings)


def run_enabled_schedulers_forever(settings: Settings | None = None) -> None:
    """Run all enabled recurring jobs in one systemd-managed process."""

    settings = settings or get_settings()
    jobs: list[ScheduledJob] = []
    if settings.reminder_enabled:
        jobs.append(ReminderScheduler(settings=settings))
    if settings.weekly_report_enabled:
        jobs.append(WeeklyReportScheduler(settings=settings))
    if not jobs:
        logger.info("no recurring Doceebot jobs are enabled")
        return

    logger.info("enabled recurring jobs: %s", ", ".join(type(job).__name__ for job in jobs))
    while True:
        candidates = [(job.next_fire_at(), job) for job in jobs]
        fire_time, job = min(
            candidates,
            key=lambda candidate: candidate[0].astimezone(UTC),
        )
        now = datetime.now(UTC)
        wait = (fire_time.astimezone(UTC) - now).total_seconds()
        logger.info(
            "next scheduled job %s in %.0fs at %s",
            type(job).__name__,
            wait,
            fire_time.isoformat(),
        )
        while wait > 0:
            step = min(wait, _POLL_STEP_SECONDS)
            time.sleep(step)
            wait -= step
        try:
            job.dispatch()
        except Exception:  # noqa: BLE001 - keep the other recurring jobs alive
            logger.exception("scheduled job %s failed", type(job).__name__)
            time.sleep(_POLL_STEP_SECONDS)
