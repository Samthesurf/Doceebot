import asyncio
import json
import logging
import threading
from hmac import compare_digest
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from whatsapp_ai_agent.config import Settings, get_settings
from whatsapp_ai_agent.core.events import InboundEvent
from whatsapp_ai_agent.db.models import InboundEventClaim, RawInboundMessage
from whatsapp_ai_agent.db.repositories import RawInboundMessageRepository
from whatsapp_ai_agent.db.session import get_session_factory
from whatsapp_ai_agent.integrations.whatsapp_meta.parser import parse_meta_webhook_payload
from whatsapp_ai_agent.integrations.whatsapp_meta.sender import MetaWhatsAppSender
from whatsapp_ai_agent.memory.tenant_scope import TenantResolution, resolve_event_tenant_scope
from whatsapp_ai_agent.security.webhooks import validate_meta_signature
from whatsapp_ai_agent.workflows.chat_processing import process_inbound_event

router = APIRouter(tags=["meta-whatsapp"])
logger = logging.getLogger(__name__)
_PLACEHOLDER_VALUES = {None, "", "change-me"}


def _require_meta_enabled(settings: Settings) -> None:
    if not settings.meta_whatsapp_enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Meta WhatsApp Cloud API is not enabled",
        )


def _media_extraction_enabled(settings: Settings) -> bool:
    return bool(settings.gemini_api_key and settings.gemini_api_key != "change-me")


def build_unresolved_scope_message(event: InboundEvent, resolution: TenantResolution) -> str:
    kind = event.message_type if event.message_type != "unknown" else "update"
    return (
        f"I received your {kind}, but I cannot store or process it yet because this WhatsApp "
        f"number is not linked to one organization ({resolution.reason}). "
        "Please link the account first."
    )


def claim_meta_event(event: InboundEvent, *, settings: Settings) -> bool:
    """Atomically reserve an event before daemon-thread dispatch.

    Meta can retry the same callback before a prior deferred turn commits its
    raw-message audit row. The separate unique claim is committed on the fast
    request path, so retrying workers and processes cannot start a second AI turn.
    """

    with get_session_factory(settings)() as db_session:
        db_session.add(
            InboundEventClaim(
                platform=event.platform,
                platform_message_id=event.platform_message_id,
            )
        )
        try:
            db_session.commit()
        except IntegrityError:
            db_session.rollback()
            return False
    return True


def release_meta_event_claim(event: InboundEvent, *, settings: Settings) -> None:
    """Remove the short-lived dispatch lock after deferred processing finishes."""

    with get_session_factory(settings)() as db_session:
        db_session.execute(
            delete(InboundEventClaim).where(
                InboundEventClaim.platform == event.platform,
                InboundEventClaim.platform_message_id == event.platform_message_id,
            )
        )
        db_session.commit()


async def process_live_meta_event(
    event: InboundEvent,
    *,
    settings: Settings,
    db_session: Session,
) -> str | None:
    """Resolve tenancy and process one Meta event with a private DB session."""

    duplicate = db_session.scalar(
        select(RawInboundMessage.id).where(
            RawInboundMessage.platform == event.platform,
            RawInboundMessage.platform_message_id == event.platform_message_id,
        )
    )
    if duplicate is not None:
        logger.info("Ignoring duplicate Meta message id=%s", event.platform_message_id)
        return None

    resolution = resolve_event_tenant_scope(event, db_session)
    if not resolution.resolved:
        RawInboundMessageRepository(db_session).add_event(event)
        db_session.commit()
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


async def process_deferred_meta_event(event: InboundEvent, *, settings: Settings) -> None:
    """Run a long Meta AI turn outside the FastAPI request event loop."""

    try:
        with get_session_factory(settings)() as db_session:
            reply_text = await process_live_meta_event(
                event,
                settings=settings,
                db_session=db_session,
            )
        if reply_text:
            await MetaWhatsAppSender(settings=settings).send_text(
                to=event.platform_chat_id,
                body=reply_text,
            )
    except Exception:
        logger.exception(
            "Deferred Meta WhatsApp processing failed for platform_message_id=%s",
            event.platform_message_id,
        )
        try:
            await MetaWhatsAppSender(settings=settings).send_text(
                to=event.platform_chat_id,
                body="Sorry, something went wrong while processing that update. Please try again.",
            )
        except Exception:
            logger.warning("Meta WhatsApp error reply failed", exc_info=True)
    finally:
        try:
            release_meta_event_claim(event, settings=settings)
        except SQLAlchemyError:
            logger.exception(
                "Could not release Meta event claim for platform_message_id=%s",
                event.platform_message_id,
            )


def dispatch_meta_event(event: InboundEvent, settings: Settings) -> None:
    """Start one private-loop daemon thread so webhook workers never block on AI."""

    def _run_deferred() -> None:
        try:
            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(process_deferred_meta_event(event, settings=settings))
            finally:
                loop.close()
        except Exception:
            logger.exception(
                "Deferred Meta WhatsApp thread failed for platform_message_id=%s",
                event.platform_message_id,
            )

    threading.Thread(target=_run_deferred, name="meta-whatsapp-deferred", daemon=True).start()


@router.get("/meta/whatsapp")
async def verify_meta_whatsapp_webhook(
    hub_mode: Annotated[str | None, Query(alias="hub.mode")] = None,
    hub_verify_token: Annotated[str | None, Query(alias="hub.verify_token")] = None,
    hub_challenge: Annotated[str | None, Query(alias="hub.challenge")] = None,
    settings: Settings = Depends(get_settings),
) -> Response:
    """Answer Meta's subscription verification request with its raw challenge."""

    _require_meta_enabled(settings)
    expected_token = settings.meta_webhook_verify_token
    if (
        hub_mode != "subscribe"
        or hub_challenge is None
        or expected_token in _PLACEHOLDER_VALUES
        or hub_verify_token is None
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid Meta webhook token",
        )
    assert expected_token is not None
    if not compare_digest(hub_verify_token, expected_token):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid Meta webhook token",
        )
    return Response(content=hub_challenge, media_type="text/plain")


@router.post("/meta/whatsapp")
async def receive_meta_whatsapp(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> dict[str, str]:
    """Authenticate, parse, and immediately acknowledge a Meta webhook callback."""

    _require_meta_enabled(settings)
    raw_body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256")
    if not validate_meta_signature(raw_body=raw_body, signature=signature, settings=settings):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid Meta signature")
    try:
        payload: Any = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload",
        ) from exc
    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Meta payload must be an object",
        )
    try:
        events = parse_meta_webhook_payload(payload, timezone_name=settings.app_timezone)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    for event in events:
        request.app.state.last_meta_event = event
        try:
            claimed = claim_meta_event(event, settings=settings)
        except SQLAlchemyError as exc:
            logger.exception(
                "Meta event claim storage unavailable for platform_message_id=%s",
                event.platform_message_id,
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Meta event storage is temporarily unavailable",
            ) from exc
        if claimed:
            dispatch_meta_event(event, settings)
        else:
            logger.info("Ignoring duplicate Meta event id=%s", event.platform_message_id)
    return {"status": "accepted"}
