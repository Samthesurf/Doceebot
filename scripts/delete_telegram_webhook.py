from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / ".env"
PLACEHOLDERS = {"", "change-me"}


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if value in PLACEHOLDERS:
        raise RuntimeError(f"{name} is not configured")
    return value


def telegram_api_post(token: str, method: str, payload: dict[str, str]) -> dict[str, object]:
    endpoint = f"https://api.telegram.org/bot{token}/{method}"
    request = Request(
        endpoint,
        data=urlencode(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "doceebot-webhook-setup",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8")
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Telegram API returned HTTP {exc.code}: {body}") from exc
    except URLError as exc:
        raise RuntimeError(f"Could not reach Telegram API: {exc.reason}") from exc

    data = json.loads(body)
    if not data.get("ok"):
        raise RuntimeError(f"Telegram API rejected the request: {data}")
    return data


def main() -> int:
    load_dotenv(ENV_FILE)
    token = require_env("TELEGRAM_BOT_TOKEN")
    telegram_api_post(token, "deleteWebhook", {"drop_pending_updates": "false"})
    print("Telegram webhook deleted.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"delete_telegram_webhook failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
