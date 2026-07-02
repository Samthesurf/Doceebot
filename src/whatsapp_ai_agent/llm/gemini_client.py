import asyncio

from google import genai
from google.genai import types

from whatsapp_ai_agent.config import Settings, get_settings
from whatsapp_ai_agent.llm.prompts import MEDIA_EXTRACTION_PROMPT
from whatsapp_ai_agent.llm.schemas import MediaExtraction
from whatsapp_ai_agent.llm.structured_output import validate_model_text


def build_gemini_client(settings: Settings | None = None) -> genai.Client:
    settings = settings or get_settings()
    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY is not configured")
    return genai.Client(api_key=settings.gemini_api_key)


class GeminiMediaExtractor:
    def __init__(
        self,
        settings: Settings | None = None,
        *,
        client: genai.Client | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.client = client or build_gemini_client(self.settings)

    def extract_media_sync(
        self,
        data: bytes,
        *,
        content_type: str,
        media_kind: str,
        filename: str | None = None,
        caption: str | None = None,
    ) -> MediaExtraction:
        prompt = "\n".join(
            part
            for part in [
                MEDIA_EXTRACTION_PROMPT,
                f"Expected media_kind: {media_kind}",
                f"Filename: {filename}" if filename else None,
                f"Caption: {caption}" if caption else None,
            ]
            if part
        )
        response = self.client.models.generate_content(
            model=self.settings.gemini_model,
            contents=[
                types.Part.from_bytes(data=data, mime_type=content_type),
                prompt,
            ],
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        )
        text = response.text or "{}"
        extraction = validate_model_text(MediaExtraction, text)
        return extraction.model_copy(update={"media_kind": media_kind})

    async def extract_media(
        self,
        data: bytes,
        *,
        content_type: str,
        media_kind: str,
        filename: str | None = None,
        caption: str | None = None,
    ) -> MediaExtraction:
        return await asyncio.to_thread(
            self.extract_media_sync,
            data,
            content_type=content_type,
            media_kind=media_kind,
            filename=filename,
            caption=caption,
        )
