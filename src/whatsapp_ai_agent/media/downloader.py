from pathlib import Path

import httpx


async def download_to_path(
    url: str,
    destination: Path,
    auth: tuple[str, str] | None = None,
) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.get(url, auth=auth)
        response.raise_for_status()
        destination.write_bytes(response.content)
    return destination
