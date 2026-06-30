# DigitalOcean PostgreSQL and Alembic setup

This is the handoff for a cloud Hermes agent deploying Doceebot to a DigitalOcean VPS.

## Goal

Set up a single low-cost VPS with:

- native PostgreSQL running locally on the VPS
- the Doceebot app using that local PostgreSQL database
- Alembic applying the project schema
- no secrets committed to Git

The database should listen only locally unless there is a deliberate private-network setup.

## Files and secrets the cloud agent will not get from GitHub

GitHub contains the code and migrations only. The cloud agent still needs these values from the user or from a secure secret store:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_WEBHOOK_SECRET_TOKEN`
- `SECRET_KEY`
- `GEMINI_API_KEY`, when AI extraction is enabled
- `DEEPSEEK_API_KEY`, when structured normalization is enabled
- Twilio credentials, when WhatsApp is enabled
- Cloudflare credentials only if the VPS will manage DNS, R2, or a Cloudflare Tunnel

The local workstation `.env` is intentionally not committed. Do not print secret values in logs or chat.

If the VPS should reuse the existing local Cloudflare named tunnel, the tunnel credentials are also not in GitHub. Prefer creating a new tunnel on the VPS, or point a Cloudflare DNS record at the VPS instead. Only transfer tunnel credential JSON if the user explicitly wants to reuse that exact tunnel.

## Recommended production shape for the low-cost VPS

```text
DigitalOcean VPS
├── PostgreSQL on localhost:5432
├── FastAPI app on localhost:8000
├── Redis/Celery later, when background jobs are wired
└── systemd services

Cloudflare
├── DNS/proxy or Cloudflare Tunnel to the VPS
└── R2 later for media, generated reports, and backups
```

Do not store voice notes, images, PDFs, DOCX, or XLSX directly in PostgreSQL. Store files in R2 or filesystem/object storage, then store only metadata and storage keys in PostgreSQL.

## 1. Prepare the VPS

Assume Ubuntu/Debian on the droplet. Run as a sudo-capable user.

```bash
sudo apt update
sudo apt install -y git curl ca-certificates postgresql postgresql-contrib
sudo systemctl enable --now postgresql
pg_isready -h 127.0.0.1 -p 5432
```

Install `uv` if it is not already present:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
uv --version
```

## 2. Clone and install the app

```bash
sudo mkdir -p /opt/doceebot
sudo chown "$USER:$USER" /opt/doceebot
git clone https://github.com/Samthesurf/Doceebot.git /opt/doceebot
cd /opt/doceebot
uv sync
```

## 3. Create local PostgreSQL database and app role

Generate a database password on the VPS. Keep it secret.

```bash
export APP_DB_PASSWORD="$(openssl rand -base64 32 | tr -d '\n')"
```

Create or update the app database role and database:

```bash
sudo -u postgres psql -v ON_ERROR_STOP=1 -v app_password="$APP_DB_PASSWORD" <<'SQL'
SELECT format('CREATE ROLE whatsapp_ai_agent LOGIN PASSWORD %L', :'app_password')
WHERE NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'whatsapp_ai_agent')\gexec
ALTER ROLE whatsapp_ai_agent WITH LOGIN PASSWORD :'app_password';
SELECT 'CREATE DATABASE whatsapp_ai_agent OWNER whatsapp_ai_agent'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'whatsapp_ai_agent')\gexec
ALTER DATABASE whatsapp_ai_agent OWNER TO whatsapp_ai_agent;
\connect whatsapp_ai_agent
ALTER SCHEMA public OWNER TO whatsapp_ai_agent;
GRANT ALL ON SCHEMA public TO whatsapp_ai_agent;
SQL
```

## 4. Create `.env` on the VPS

Start from the example file and edit values. Never commit this file.

```bash
cd /opt/doceebot
cp .env.example .env
python - <<'PY'
from pathlib import Path
from secrets import token_urlsafe
import os
from urllib.parse import quote

path = Path('.env')
lines = path.read_text().splitlines()
updates = {
    'APP_ENV': 'production',
    'APP_BASE_URL': 'https://doceebot.name.ng',
    'SECRET_KEY': token_urlsafe(48),
    'DATABASE_URL': 'postgresql+psycopg://whatsapp_ai_agent:'
        + quote(os.environ['APP_DB_PASSWORD'])
        + '@localhost:5432/whatsapp_ai_agent',
}
seen = set()
out = []
for line in lines:
    if '=' in line and not line.lstrip().startswith('#'):
        key = line.split('=', 1)[0]
        if key in updates:
            out.append(f'{key}={updates[key]}')
            seen.add(key)
        else:
            out.append(line)
    else:
        out.append(line)
for key, value in updates.items():
    if key not in seen:
        out.append(f'{key}={value}')
path.write_text('\n'.join(out) + '\n')
PY
```

Then fill in the real channel/API secrets in `.env`:

```bash
nano .env
```

Required before live Telegram testing:

```text
TELEGRAM_BOT_TOKEN=...
TELEGRAM_WEBHOOK_SECRET_TOKEN=...
APP_BASE_URL=https://doceebot.name.ng
```

Required later for Twilio/AI/R2:

```text
TWILIO_ACCOUNT_SID=...
TWILIO_AUTH_TOKEN=...
TWILIO_WHATSAPP_FROM=...
GEMINI_API_KEY=...
DEEPSEEK_API_KEY=...
```

## 5. Apply Alembic migrations

```bash
cd /opt/doceebot
uv run alembic upgrade head
uv run alembic current
uv run alembic check
```

Expected current revision after this setup:

```text
20260630_0001 (head)
```

Verify tables:

```bash
uv run python - <<'PY'
from sqlalchemy import inspect, text
from whatsapp_ai_agent.db.session import get_engine

expected = {
    'alembic_version',
    'organizations',
    'users',
    'memberships',
    'raw_inbound_messages',
    'work_log_entries',
}
with get_engine().connect() as conn:
    tables = set(inspect(conn).get_table_names())
    version = conn.execute(text('select version_num from alembic_version')).scalar_one()
print('alembic_version=' + version)
print('missing=' + ','.join(sorted(expected - tables)) if expected - tables else 'missing=none')
PY
```

## 6. Run verification

```bash
uv run ruff check .
uv run pytest
uv run uvicorn whatsapp_ai_agent.main:app --host 127.0.0.1 --port 8000
```

In another shell:

```bash
curl -fsS http://127.0.0.1:8000/health
```

## 7. Expose the app

Use one of these approaches.

### Option A: Cloudflare DNS/proxy to VPS

Point `doceebot.name.ng` to the droplet public IP in Cloudflare, then run a reverse proxy such as Caddy or Nginx from HTTPS to `127.0.0.1:8000`.

### Option B: Cloudflare Tunnel on VPS

Install `cloudflared`, create a new named tunnel on the VPS, route `doceebot.name.ng` to it, and point ingress to `http://localhost:8000`.

Do not assume the local workstation tunnel credentials exist on the VPS. They are intentionally outside Git.

## 8. Telegram webhook after deploy

After `APP_BASE_URL` and Telegram secrets are set on the VPS:

```bash
cd /opt/doceebot
uv run python scripts/set_telegram_webhook.py
```

Then verify with a real Telegram message and app logs.

## 9. Backups

For local PostgreSQL on a cheap VPS, off-server backups are mandatory.

Basic manual backup:

```bash
pg_dump "$DATABASE_URL" | gzip > "doceebot-$(date +%F-%H%M).sql.gz"
```

Long term, upload backups to Cloudflare R2 or another off-server storage target and add a cron/systemd timer.
