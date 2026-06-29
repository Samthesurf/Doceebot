from whatsapp_ai_agent.workers.celery_app import celery_app


@celery_app.task(name="summaries.refresh")
def refresh_summary_task(summary_request: dict) -> dict:
    return {"status": "queued", "request": summary_request}
