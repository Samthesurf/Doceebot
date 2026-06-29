def select_reporting_skill(message_text: str) -> str:
    lowered = message_text.lower()
    if "excel" in lowered or "xlsx" in lowered:
        return "excel_work_log"
    return "default_engineering_report"
