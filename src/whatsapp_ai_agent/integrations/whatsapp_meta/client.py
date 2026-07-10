from urllib.parse import quote

from whatsapp_ai_agent.config import Settings


def meta_graph_api_url(settings: Settings, *path_parts: str) -> str:
    base_url = settings.meta_graph_api_base_url.rstrip("/")
    version = settings.meta_graph_api_version.strip("/")
    if not base_url or not version:
        raise RuntimeError("META_GRAPH_API_BASE_URL and META_GRAPH_API_VERSION are required")
    encoded_path = "/".join(quote(str(part).strip("/"), safe="") for part in path_parts)
    return f"{base_url}/{version}/{encoded_path}"


def meta_auth_headers(settings: Settings) -> dict[str, str]:
    access_token = settings.meta_access_token
    if not access_token or access_token == "change-me":
        raise RuntimeError("META_ACCESS_TOKEN is not configured")
    return {"Authorization": f"Bearer {access_token}"}
