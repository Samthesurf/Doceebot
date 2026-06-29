from pathlib import Path

from openpyxl import Workbook

from whatsapp_ai_agent.documents.schemas import WorkbookSpec


def generate_xlsx_workbook(spec: WorkbookSpec, output_path: Path) -> Path:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = spec.title[:31]
    sheet.append(["Date", "Worker", "Project", "Summary"])
    for row in spec.rows:
        sheet.append([row.date, row.worker, row.project, row.summary])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(output_path)
    return output_path
