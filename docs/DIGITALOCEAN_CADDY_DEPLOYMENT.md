# DigitalOcean deployment with Caddy

This guide turns a freshly cloned Doceebot checkout into a small production deployment on a DigitalOcean Ubuntu droplet.

## Runtime shape

```text
Cloudflare DNS or proxy
        |
        v
Caddy on ports 80 and 443
        |
        v
FastAPI on 127.0.0.1:8000
        |
        v
PostgreSQL on 127.0.0.1:5432
```

Caddy is the preferred reverse proxy for this project. Nginx is not required.

## 1. Create the app user and install packages

```bash
sudo apt update
sudo apt install -y git curl ca-certificates postgresql postgresql-contrib caddy
sudo systemctl enable --now postgresql
sudo useradd --system --create-home --home-dir /opt/doceebot --shell /usr/sbin/nologin doceebot || true
```

## 2. Place the app under `/opt/doceebot`

For a fresh droplet:

```bash
sudo rm -rf /opt/doceebot
sudo git clone https://github.com/Samthesurf/Doceebot.git /opt/doceebot
sudo chown -R doceebot:doceebot /opt/doceebot
```

Install `uv` for root or for the deployment user, then sync dependencies:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
cd /opt/doceebot
sudo -u doceebot env PATH="$PATH" uv sync
```

## 3. Configure PostgreSQL and `.env`

Follow `docs/DIGITALOCEAN_POSTGRES_ALEMBIC.md` to create the `whatsapp_ai_agent` role and database. The app database URL must use the app role, not the `postgres` superuser.

Minimum production settings in `/opt/doceebot/.env`:

```env
APP_ENV=production
APP_BASE_URL=https://doceebot.name.ng
SECRET_KEY=<generated-secret>
DATABASE_URL=postgresql+psycopg://whatsapp_ai_agent:<database-password>@localhost:5432/whatsapp_ai_agent
TWILIO_WEBHOOK_AUTH_ENABLED=true
TWILIO_AUTH_TOKEN=<real-twilio-auth-token>
TELEGRAM_WEBHOOK_SECRET_TOKEN=<generated-telegram-webhook-secret>
TELEGRAM_BOT_TOKEN=<real-bot-token>
```

Keep the file private:

```bash
sudo chown doceebot:doceebot /opt/doceebot/.env
sudo chmod 600 /opt/doceebot/.env
```

## 4. Run migrations and checks

```bash
cd /opt/doceebot
sudo -u doceebot .venv/bin/alembic upgrade head
sudo -u doceebot .venv/bin/alembic current
sudo -u doceebot .venv/bin/alembic check
sudo -u doceebot .venv/bin/python - <<'PY'
from sqlalchemy import inspect, text
from whatsapp_ai_agent.db.session import get_engine
expected = {'alembic_version', 'organizations', 'users', 'memberships', 'raw_inbound_messages', 'work_log_entries'}
with get_engine().connect() as conn:
    tables = set(inspect(conn).get_table_names())
    version = conn.execute(text('select version_num from alembic_version')).scalar_one()
print('alembic_version=' + version)
print('missing=' + (','.join(sorted(expected - tables)) if expected - tables else 'none'))
PY
```

## 5. Install the systemd service

Copy the checked-in service template:

```bash
sudo cp /opt/doceebot/deploy/doceebot.service /etc/systemd/system/doceebot.service
sudo systemctl daemon-reload
sudo systemctl enable --now doceebot
sudo systemctl status doceebot --no-pager
curl -fsS http://127.0.0.1:8000/health
```

The service binds only to localhost. Caddy is responsible for public HTTPS.

## 6. Configure Caddy

Point `doceebot.name.ng` at the droplet in Cloudflare first. Then install the Caddyfile:

```bash
sudo cp /opt/doceebot/deploy/Caddyfile /etc/caddy/Caddyfile
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

Verify locally on the droplet:

```bash
curl -fsS -H 'Host: doceebot.name.ng' http://127.0.0.1/health
```

Verify from outside after DNS is ready:

```bash
curl -fsS https://doceebot.name.ng/health
```

If Cloudflare proxy mode blocks certificate issuance, temporarily set the DNS record to DNS-only until Caddy obtains its certificate, or use the Cloudflare DNS challenge with a Caddy build that includes the Cloudflare DNS provider.

## 7. Set the Telegram webhook

Only run this after `APP_BASE_URL`, `TELEGRAM_BOT_TOKEN`, and `TELEGRAM_WEBHOOK_SECRET_TOKEN` are real values:

```bash
cd /opt/doceebot
sudo -u doceebot .venv/bin/python scripts/set_telegram_webhook.py
```

Then send a real Telegram message and inspect logs:

```bash
sudo journalctl -u doceebot -f
```

## 8. Backup reminder

Local PostgreSQL on a cheap VPS needs off-server backups. Start with:

```bash
sudo -u doceebot bash -lc 'source /opt/doceebot/.env && pg_dump "$DATABASE_URL" | gzip > "/opt/doceebot/storage/doceebot-$(date +%F-%H%M).sql.gz"'
```

Then move backup archives to Cloudflare R2 or another off-server storage target.
