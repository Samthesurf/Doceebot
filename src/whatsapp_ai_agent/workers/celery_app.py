from celery import Celery

from whatsapp_ai_agent.config import Settings, get_settings

celery_app = Celery("whatsapp_ai_agent")
_is_configured = False


def configure_celery_app(settings: Settings | None = None) -> Celery:
    """Configure Celery lazily so importing task modules has no settings side effects."""

    global _is_configured
    if not _is_configured:
        settings = settings or get_settings()
        celery_app.conf.update(
            broker_url=settings.redis_url,
            result_backend=settings.redis_url,
        )
        _is_configured = True
    return celery_app
