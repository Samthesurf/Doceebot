from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from whatsapp_ai_agent.config import Settings, get_settings
from whatsapp_ai_agent.core.events import InboundEvent
from whatsapp_ai_agent.db.session import get_db_session
from whatsapp_ai_agent.integrations.whatsapp_twilio.parser import parse_twilio_whatsapp_form
from whatsapp_ai_agent.integrations.whatsapp_twilio.twiml import text_messaging_response
from whatsapp_ai_agent.memory.tenant_scope import TenantResolution, resolve_event_tenant_scope
from whatsapp_ai_agent.security.webhooks import validate_twilio_request
from whatsapp_ai_agent.workflows.chat_processing import process_inbound_event

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


@router.post("/twilio/whatsapp")
async def receive_twilio_whatsapp(
    request: Request,
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
    body = await process_live_twilio_event(event, settings=settings, db_session=db_session)
    return Response(content=text_messaging_response(body), media_type="application/xml")
