from whatsapp_ai_agent.llm.schemas import NormalizedWorkLog


def work_log_summary(log: NormalizedWorkLog) -> str:
    return log.summary.strip()
