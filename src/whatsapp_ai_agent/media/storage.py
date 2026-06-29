from pathlib import Path

from whatsapp_ai_agent.config import Settings, get_settings


class LocalStorage:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.root = Path(self.settings.local_storage_dir)

    def path_for(self, *parts: str) -> Path:
        path = self.root.joinpath(*parts)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path
