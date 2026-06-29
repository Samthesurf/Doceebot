import httpx

from whatsapp_ai_agent.config import Settings, get_settings


class CloudflareAIClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        if not self.settings.cloudflare_api_token:
            raise RuntimeError("CLOUDFLARE_API_TOKEN is not configured")
        self.http = httpx.AsyncClient(
            headers={"Authorization": f"Bearer {self.settings.cloudflare_api_token}"},
            timeout=60,
        )

    async def aclose(self) -> None:
        await self.http.aclose()

    async def __aenter__(self) -> "CloudflareAIClient":
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()
