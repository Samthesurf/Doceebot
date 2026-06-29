from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from whatsapp_ai_agent.config import Settings, get_settings
from whatsapp_ai_agent.integrations.whatsapp_twilio.parser import parse_twilio_whatsapp_form
from whatsapp_ai_agent.integrations.whatsapp_twilio.twiml import empty_messaging_response
from whatsapp_ai_agent.security.webhooks import validate_twilio_request

router = APIRouter(tags=["twilio-whatsapp"])


def _public_url_for_request(request: Request, settings: Settings) -> str:
    base_url = settings.app_base_url.rstrip("/")
    return f"{base_url}{request.url.path}"


@router.post("/twilio/whatsapp")
async def receive_twilio_whatsapp(
    request: Request,
    settings: Settings = Depends(get_settings),
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

    return Response(content=empty_messaging_response(), media_type="application/xml")
