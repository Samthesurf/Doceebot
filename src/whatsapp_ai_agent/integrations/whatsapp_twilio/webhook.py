import asyncio
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from whatsapp_ai_agent.config import Settings, get_settings
from whatsapp_ai_agent.core.events import InboundEvent
from whatsapp_ai_agent.db.session import get_db_session, get_session_factory
from whatsapp_ai_agent.integrations.whatsapp_twilio.client import build_twilio_client
from whatsapp_ai_agent.integrations.whatsapp_twilio.parser import parse_twilio_whatsapp_form
from whatsapp_ai_agent.integrations.whatsapp_twilio.twiml import text_messaging_response
from whatsapp_ai_agent.memory.tenant_scope import TenantResolution, resolve_event_tenant_scope
from whatsapp_ai_agent.security.webhooks import validate_twilio_request
from whatsapp_ai_agent.workflows.chat_processing import process_inbound_event

logger = logging.getLogger(__name__)

router = APIRouter(tags=["twilio-whatsapp"])


def _public_url_for_request(request: Request, settings: Settings) -> str:
    base_url = settings.app_base_url.rstrip("/")
    return f"{base_url}{request.url.path}"


def build_twilio_acknowledgement(event: InboundEvent) -> str:
    if event.media:
        return (
            f"I received your {event.message_type} upload. I will extract the useful work details, "
            "save it as a draft log, then ask only the missing follow-up questions."
        )
    return (
        "I received your work update. I will turn it into a draft log "
        "and ask for any missing details."
    )


def build_unresolved_scope_message(event: InboundEvent, resolution: TenantResolution) -> str:
    return (
        f"{build_twilio_acknowledgement(event)}\n\n"
        "I cannot store or process the upload yet because this WhatsApp number is not linked "
        f"to one organization ({resolution.reason}). Please link the account first."
    )


def _media_extraction_enabled(settings: Settings) -> bool:
    return bool(settings.gemini_api_key and settings.gemini_api_key != "change-me")


async def process_live_twilio_event(
    event: InboundEvent,
    *,
    settings: Settings,
    db_session: Session,
) -> str:
    resolution = resolve_event_tenant_scope(event, db_session)
    if not resolution.resolved:
        return build_unresolved_scope_message(event, resolution)

    result = await process_inbound_event(
        resolution.event,
        settings=settings,
        db_session=db_session,
        download_media=True,
        extract_media=_media_extraction_enabled(settings),
    )
    db_session.commit()
    return result.reply_text


async def send_twilio_text_reply(
    event: InboundEvent,
    body: str,
    *,
    settings: Settings,
) -> None:
    """Send a follow-up WhatsApp message with Twilio's REST API.

    Twilio expects webhook handlers to respond quickly. Media messages often need
    download, Gemini extraction, and LLM parsing, so the webhook returns a fast
    TwiML acknowledgement and this helper sends the real result afterwards.
    """

    create_kwargs: dict[str, str] = {
        "to": event.platform_chat_id,
        "body": body,
    }
    if settings.twilio_messaging_service_sid:
        create_kwargs["messaging_service_sid"] = settings.twilio_messaging_service_sid
    elif settings.twilio_whatsapp_from:
        create_kwargs["from_"] = settings.twilio_whatsapp_from
    else:
        raise RuntimeError("TWILIO_WHATSAPP_FROM or TWILIO_MESSAGING_SERVICE_SID is required")

    client = build_twilio_client(settings)
    await asyncio.to_thread(client.messages.create, **create_kwargs)


async def send_twilio_typing_indicator(event: InboundEvent, *, settings: Settings) -> None:
    """Show the native WhatsApp 'typing…' indicator on Twilio.

    Twilio anchors the indicator to the inbound message SID (SM*/MM*), so the
    event's platform_message_id must be a valid Twilio message SID. The indicator
    expires after a short window, so callers should refresh it (see
    ``twilio_typing``). Raises on failure so callers can fall back to a text
    message.
    """

    if not event.platform_message_id or not event.platform_message_id.startswith(("SM", "MM")):
        raise ValueError("event.platform_message_id is not a valid Twilio message SID")

    client = build_twilio_client(settings)
    await asyncio.to_thread(
        client.messaging.v2.typing_indicator.create,
        channel="whatsapp",
        message_id=event.platform_message_id,
    )


class _TwilioTypingIndicator:
    """Keep the WhatsApp 'typing…' indicator alive for the duration of a block.

    Twilio's typing indicator expires after a short period (well under the 10 to
    15 second AI turn), so this refreshes it on an interval. If the very first
    send fails (for example a non-Twilio SID), the context manager falls back to
    a one-time 'thinking' text message instead of raising.
    """

    _REFRESH_INTERVAL_SECONDS = 20

    def __init__(self, event: InboundEvent, *, settings: Settings) -> None:
        self._event = event
        self._settings = settings
        self._task: asyncio.Task[None] | None = None
        self._fallback_sent = False

    async def __aenter__(self) -> "_TwilioTypingIndicator":
        try:
            await send_twilio_typing_indicator(self._event, settings=self._settings)
        except Exception:
            logger.warning("Twilio typing indicator failed; using text fallback", exc_info=True)
            await self._send_text_fallback()
            return self
        self._task = asyncio.create_task(self._refresh_loop())
        return self

    async def __aexit__(
        self,
        exc_type: object,
        exc: object,
        tb: object,
    ) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass

    async def _refresh_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(self._REFRESH_INTERVAL_SECONDS)
                await send_twilio_typing_indicator(self._event, settings=self._settings)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("Twilio typing refresh failed; using text fallback", exc_info=True)
            if not self._fallback_sent:
                await self._send_text_fallback()

    async def _send_text_fallback(self) -> None:
        if self._fallback_sent or self._event.media:
            return
        self._fallback_sent = True
        try:
            await send_twilio_text_reply(
                self._event, _INTERIM_THINKING_MESSAGE, settings=self._settings
            )
        except Exception:
            logger.warning("Twilio text fallback failed", exc_info=True)


def twilio_typing(event: InboundEvent, *, settings: Settings) -> _TwilioTypingIndicator:
    """Return a context manager that keeps the WhatsApp typing indicator on."""
    return _TwilioTypingIndicator(event, settings=settings)


async def process_deferred_twilio_event(event: InboundEvent, *, settings: Settings) -> None:
    """Process a Twilio event after the webhook response has already been sent.

    Twilio expects webhook handlers to respond quickly. Media messages need
    download, Gemini extraction, and LLM parsing, and text turns also take 10 to
    15 seconds for the AI parse, so the webhook returns a fast TwiML
    acknowledgement and this helper sends the real result afterwards. For text
    turns it shows the native WhatsApp 'typing…' indicator (with a 'thinking'
    text message as a fallback) so the chat never sits blank.
    """

    # Show the native typing indicator for the whole AI turn. Twilio's indicator
    # expires quickly, so the context manager refreshes it on an interval. Media
    # uploads have their own progress state, so only use it for text turns.
    typing_cm = twilio_typing(event, settings=settings) if not event.media else None

    async def _run() -> None:
        try:
            with get_session_factory(settings)() as db_session:
                body = await process_live_twilio_event(
                    event,
                    settings=settings,
                    db_session=db_session,
                )
            await send_twilio_text_reply(event, body, settings=settings)
        except Exception:
            logger.exception(
                "Deferred Twilio WhatsApp processing failed for platform_message_id=%s",
                event.platform_message_id,
            )
            try:
                await send_twilio_text_reply(
                    event,
                    "Sorry, something went wrong while processing that update. Please try again.",
                    settings=settings,
                )
            except Exception:
                logger.warning("Twilio error reply failed", exc_info=True)

    if typing_cm is not None:
        async with typing_cm:
            await _run()
    else:
        await _run()


@router.post("/twilio/whatsapp")
async def receive_twilio_whatsapp(
    request: Request,
    background_tasks: BackgroundTasks,
    settings: Settings = Depends(get_settings),
    db_session: Session = Depends(get_db_session),
) -> Response:
    form_data = await request.form()
    form = {str(key): str(value) for key, value in form_data.items()}
    signature = request.headers.get("X-Twilio-Signature")

    if not validate_twilio_request(
        url=_public_url_for_request(request, settings),
        form=form,
        signature=signature,
        settings=settings,
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid Twilio signature",
        )

    event = parse_twilio_whatsapp_form(form, timezone_name=settings.app_timezone)
    request.app.state.last_twilio_event = event

    # Twilio expects webhook handlers to respond quickly (long handling triggers
    # retries). Acknowledge fast with a TwiML message, then run the slow AI turn
    # in the background and deliver the real reply as a follow-up. The deferred
    # task shows the native WhatsApp typing indicator (with a "thinking" text
    # message as a fallback) for text turns.
    background_tasks.add_task(process_deferred_twilio_event, event, settings=settings)
    return Response(
        content=text_messaging_response(build_twilio_acknowledgement(event)),
        media_type="application/xml",
    )


_INTERIM_THINKING_MESSAGE = (
    "Got it, working on that now. Give me a few seconds and I will send your draft."
)

