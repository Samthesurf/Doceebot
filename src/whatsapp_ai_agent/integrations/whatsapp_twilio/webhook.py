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


async def refresh_twilio_typing_indicator(event: InboundEvent, *, settings: Settings) -> None:
    """Best-effort: show the native typing indicator without ever blocking the reply.

    This is fire-and-forget. It sends the indicator immediately and refreshes it
    on an interval, but any failure (slow API, invalid SID, auth error) is logged
    and swallowed, with a one-time 'thinking' text as a fallback. It must never
    delay the actual AI turn or the reply, which is why the caller runs it
    concurrently with processing rather than awaiting it up front.
    """

    try:
        await send_twilio_typing_indicator(event, settings=settings)
    except Exception:
        logger.warning("Twilio typing indicator unavailable", exc_info=True)
        await send_twilio_thinking_ack(event, settings=settings)
        return
    try:
        while True:
            await asyncio.sleep(_TYPING_REFRESH_INTERVAL_SECONDS)
            await send_twilio_typing_indicator(event, settings=settings)
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.warning("Twilio typing indicator refresh failed", exc_info=True)
        await send_twilio_thinking_ack(event, settings=settings)


_TYPING_REFRESH_INTERVAL_SECONDS = 20


async def send_twilio_thinking_ack(event: InboundEvent, *, settings: Settings) -> None:
    """Send the one-time 'thinking' text acknowledgement (fallback for typing)."""

    if event.media:
        return
    try:
        await send_twilio_text_reply(event, _INTERIM_THINKING_MESSAGE, settings=settings)
    except Exception:
        logger.warning("Twilio thinking acknowledgement failed", exc_info=True)


async def process_deferred_twilio_event(event: InboundEvent, *, settings: Settings) -> None:
    """Process a Twilio event after the webhook response has already been sent.

    Twilio expects webhook handlers to respond quickly. Media messages need
    download, Gemini extraction, and LLM parsing, and text turns also take 10 to
    15 seconds for the AI parse, so the webhook returns a fast TwiML
    acknowledgement and this helper sends the real result afterwards. For text
    turns it shows the native WhatsApp 'typing…' indicator (with a 'thinking'
    text message as a fallback) so the chat never sits blank.
    """

    # Show the visible acknowledgement concurrently with the AI turn. The typing
    # indicator (with a 'thinking' text fallback) must NEVER block or delay the
    # model call or the reply. It runs as its own task so the first send and the
    # model call happen in parallel; we await it at the end only to clean up, and
    # any failure is swallowed. Previously the typing call ran up front and, when
    # Twilio's API was slow, pushed the whole reply back by several seconds.
    typing_task: asyncio.Task[None] | None = None
    if not event.media:
        typing_task = asyncio.create_task(
            refresh_twilio_typing_indicator(event, settings=settings)
        )

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
    finally:
        if typing_task is not None:
            typing_task.cancel()
            try:
                await typing_task
            except (asyncio.CancelledError, Exception):
                pass


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

