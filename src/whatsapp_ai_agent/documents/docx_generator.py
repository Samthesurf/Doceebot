from pathlib import Path

from docx import Document

from whatsapp_ai_agent.documents.schemas import ReportSpec


def generate_docx_report(spec: ReportSpec, output_path: Path) -> Path:
    document = Document()
    document.add_heading(spec.title, level=1)
    for section in spec.sections:
        document.add_heading(section.heading, level=2)
        for paragraph in section.paragraphs:
            document.add_paragraph(paragraph)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    document.save(output_path)
    return output_path
