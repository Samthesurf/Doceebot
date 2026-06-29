import httpx

from whatsapp_ai_agent.config import Settings, get_settings


class DeepSeekClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        if not self.settings.deepseek_api_key:
            raise RuntimeError("DEEPSEEK_API_KEY is not configured")
        self.http = httpx.AsyncClient(
            base_url="https://api.deepseek.com",
            headers={"Authorization": f"Bearer {self.settings.deepseek_api_key}"},
            timeout=60,
        )

    async def aclose(self) -> None:
        await self.http.aclose()

    async def __aenter__(self) -> "DeepSeekClient":
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()
