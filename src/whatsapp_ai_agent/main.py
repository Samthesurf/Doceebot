import uvicorn
from fastapi import FastAPI

from whatsapp_ai_agent.api.dashboard import router as dashboard_router
from whatsapp_ai_agent.api.documents import router as documents_router
from whatsapp_ai_agent.api.health import router as health_router
from whatsapp_ai_agent.config import Settings, get_settings
from whatsapp_ai_agent.integrations.telegram.webhook import router as telegram_router
from whatsapp_ai_agent.integrations.whatsapp_meta.webhook import router as meta_router
from whatsapp_ai_agent.integrations.whatsapp_twilio.webhook import router as twilio_router


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title=settings.app_name, version=settings.app_version)

    app.include_router(health_router)
    app.include_router(dashboard_router)
    app.include_router(documents_router)
    app.include_router(twilio_router, prefix="/webhooks")
    app.include_router(meta_router, prefix="/webhooks")
    app.include_router(telegram_router, prefix="/webhooks")

    @app.get("/", tags=["health"])
    def root() -> dict[str, str]:
        return {"service": settings.app_name, "status": "ok"}

    return app


app = create_app()


def run() -> None:
    settings = get_settings()
    uvicorn.run(
        "whatsapp_ai_agent.main:app",
        host="0.0.0.0",
        port=8000,
        reload=not settings.is_production,
    )
