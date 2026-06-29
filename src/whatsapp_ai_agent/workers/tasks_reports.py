from whatsapp_ai_agent.workers.celery_app import celery_app


@celery_app.task(name="reports.generate")
def generate_report_task(report_request: dict) -> dict:
    return {"status": "queued", "request": report_request}
