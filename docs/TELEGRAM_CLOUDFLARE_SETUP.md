# Telegram + Cloudflare Tunnel Setup

This guide connects the local Doceebot FastAPI server to Telegram through Cloudflare Tunnel.

## Important secret rule

Do not commit `.env`.

The bot token belongs only in your local `.env` file or in a production secret manager. The repo only contains `.env.example` placeholders.

## Option A: Cloudflare Quick Tunnel, recommended first

This does not require a Cloudflare domain or login. It gives a temporary `trycloudflare.com` URL.

### 1. Create local `.env`

From the project root:

```bash
uv run python scripts/dev_init_env.py
```

This creates `.env` if it does not already exist. It also generates local values for:

- `SECRET_KEY`
- `TELEGRAM_WEBHOOK_SECRET_TOKEN`

Now open `.env` and set:

```text
TELEGRAM_BOT_TOKEN=<paste BotFather token here>
```

Leave Twilio values blank for now.

### 2. Start the FastAPI app

Terminal 1:

```bash
uv run uvicorn whatsapp_ai_agent.main:app --reload
```

Check:

```bash
curl http://localhost:8000/health
```

Expected result includes:

```json
{"status":"ok"}
```

### 3. Start Cloudflare Quick Tunnel

Terminal 2:

```bash
./scripts/cloudflare_quick_tunnel.sh
```

Cloudflare will print an HTTPS URL like:

```text
https://example.trycloudflare.com
```

Copy that full HTTPS URL.

### 4. Update `.env`

Set:

```text
APP_BASE_URL=https://example.trycloudflare.com
```

Use the actual URL Cloudflare printed.

### 5. Restart the FastAPI app

Stop the FastAPI app in Terminal 1 with `Ctrl+C`, then start it again:

```bash
uv run uvicorn whatsapp_ai_agent.main:app --reload
```

This reloads `APP_BASE_URL` from `.env`.

### 6. Register Telegram webhook

Terminal 3:

```bash
uv run python scripts/set_telegram_webhook.py
```

Expected output:

```text
Telegram webhook set to: https://example.trycloudflare.com/webhooks/telegram/webhook
Telegram secret-token header is enabled.
```

### 7. Test the bot

Send a message to the bot in Telegram.

The current scaffold accepts and parses incoming Telegram messages, but it does not yet send useful replies. The next implementation step is adding Telegram handlers that turn those events into work-log actions.

## Option B: Named Cloudflare Tunnel with your own domain

Use this when you want a stable URL such as:

```text
https://doceebot.yourdomain.com
```

Requirements:

- A domain in your Cloudflare account.
- `cloudflared` logged into Cloudflare.

### 1. Log in

```bash
cloudflared tunnel login
```

This opens a browser. Choose the Cloudflare account and domain.

### 2. Create a named tunnel

```bash
cloudflared tunnel create doceebot-dev
```

Cloudflare prints a tunnel ID. Save it.

### 3. Route DNS

Replace `doceebot.yourdomain.com` with your real hostname:

```bash
cloudflared tunnel route dns doceebot-dev doceebot.yourdomain.com
```

### 4. Create tunnel config

Create `~/.cloudflared/doceebot-dev.yml`:

```yaml
tunnel: <TUNNEL_ID>
credentials-file: /home/samuelsurf/.cloudflared/<TUNNEL_ID>.json

ingress:
  - hostname: doceebot.yourdomain.com
    service: http://localhost:8000
  - service: http_status:404
```

### 5. Run the tunnel

```bash
cloudflared tunnel --config ~/.cloudflared/doceebot-dev.yml run doceebot-dev
```

Then set in `.env`:

```text
APP_BASE_URL=https://doceebot.yourdomain.com
```

Restart FastAPI and run:

```bash
uv run python scripts/set_telegram_webhook.py
```

## Useful commands

Delete webhook and return to polling mode later:

```bash
uv run python scripts/delete_telegram_webhook.py
```

Check current webhook info manually, without printing the token:

```bash
uv run python - <<'PY'
import os
from pathlib import Path
from urllib.request import urlopen

for line in Path('.env').read_text().splitlines():
    if '=' in line and not line.startswith('#'):
        k, v = line.split('=', 1)
        os.environ.setdefault(k, v)

token = os.environ['TELEGRAM_BOT_TOKEN']
with urlopen(f'https://api.telegram.org/bot{token}/getWebhookInfo') as response:
    print(response.read().decode())
PY
```

## Troubleshooting

- If Telegram says the webhook URL is bad, confirm `APP_BASE_URL` starts with `https://`.
- If messages do not arrive, confirm FastAPI and `cloudflared` are both still running.
- If Cloudflare Quick Tunnel gives a new URL after restart, update `APP_BASE_URL`, restart FastAPI, and run `set_telegram_webhook.py` again.
- If the webhook secret fails, generate a new `TELEGRAM_WEBHOOK_SECRET_TOKEN` in `.env` and re-run `set_telegram_webhook.py`.
