from whatsapp_ai_agent.workers.celery_app import celery_app


@celery_app.task(name="ingest.inbound_event")
def ingest_inbound_event(event_payload: dict) -> dict:
    return {"status": "queued", "platform": event_payload.get("platform")}
