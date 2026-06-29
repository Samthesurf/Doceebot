from __future__ import annotations

import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_EXAMPLE = ROOT / ".env.example"
ENV_FILE = ROOT / ".env"

RANDOMIZED_KEYS = {
    "SECRET_KEY": lambda: secrets.token_urlsafe(48),
    "TELEGRAM_WEBHOOK_SECRET_TOKEN": lambda: secrets.token_urlsafe(32),
}


def parse_env_lines(text: str) -> list[str]:
    lines: list[str] = []
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#") or "=" not in line:
            lines.append(line)
            continue
        key, value = line.split("=", 1)
        if key in RANDOMIZED_KEYS and value in {"", "change-me"}:
            lines.append(f"{key}={RANDOMIZED_KEYS[key]()}")
        else:
            lines.append(line)
    return lines


def main() -> int:
    if ENV_FILE.exists():
        print(".env already exists. I did not overwrite it.")
        return 0

    text = ENV_EXAMPLE.read_text(encoding="utf-8")
    ENV_FILE.write_text("\n".join(parse_env_lines(text)) + "\n", encoding="utf-8")
    print("Created .env from .env.example.")
    print("Generated local SECRET_KEY and TELEGRAM_WEBHOOK_SECRET_TOKEN values.")
    print("Next: open .env and set TELEGRAM_BOT_TOKEN and APP_BASE_URL.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
