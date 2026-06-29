from google import genai

from whatsapp_ai_agent.config import Settings, get_settings


def build_gemini_client(settings: Settings | None = None) -> genai.Client:
    settings = settings or get_settings()
    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY is not configured")
    return genai.Client(api_key=settings.gemini_api_key)
