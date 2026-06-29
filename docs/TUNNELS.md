# Local Tunnel Crash Course

A tunnel gives a local development server a temporary public internet address.

For this project, FastAPI runs on your laptop at something like:

```text
http://localhost:8000
```

Telegram and Twilio are cloud services. They cannot call `localhost` on your laptop because, from their point of view, `localhost` means their own server, not your machine. A tunnel solves that by creating a public HTTPS URL such as:

```text
https://example.ngrok-free.app
```

or:

```text
https://bot.example.com
```

The tunnel forwards traffic from that public URL into your local FastAPI server.

## How we use it

1. Start the FastAPI app locally:

```bash
uv run uvicorn whatsapp_ai_agent.main:app --reload
```

2. Start a tunnel that points to local port 8000.

3. Put the tunnel URL into Telegram or Twilio webhook settings.

For Telegram, the webhook URL will look like:

```text
https://your-tunnel-url/webhooks/telegram/webhook
```

For Twilio WhatsApp, the webhook URL will look like:

```text
https://your-tunnel-url/webhooks/twilio/whatsapp
```

When someone messages the bot, Telegram or Twilio sends an HTTPS request to the tunnel URL. The tunnel forwards that request into the local FastAPI app.

## Why we need HTTPS

Telegram and Twilio expect publicly reachable HTTPS webhook URLs. A normal local server is private and usually HTTP only. The tunnel gives us public HTTPS without deploying the app to a real server yet.

## ngrok

ngrok is the easiest option for quick development.

Pros:

- Very fast to start.
- Common tutorials and examples.
- Good request inspection dashboard.
- Fine for testing Telegram and Twilio webhooks.

Cons:

- Free URLs may change when restarted.
- Some advanced features need a paid account.
- You depend on ngrok for the public URL.

Typical use:

```bash
ngrok http 8000
```

Then copy the HTTPS forwarding URL into `.env` as `APP_BASE_URL` and into the Telegram or Twilio webhook configuration.

## Cloudflare Tunnel

Cloudflare Tunnel is better when you want something more stable or closer to production.

Pros:

- Can use your own domain, for example `bot.yourdomain.com`.
- Very good for long-lived development and staging.
- Works well if production will already use Cloudflare.
- Does not require opening inbound ports on the machine.

Cons:

- Initial setup is more involved.
- Best experience requires a domain on Cloudflare.
- Less beginner-friendly than ngrok for quick tests.

Typical use after setup:

```bash
cloudflared tunnel --url http://localhost:8000
```

For a named tunnel with your own domain, Cloudflare setup is required first.

## Which one should we use now?

For this project, use ngrok first unless you already have a Cloudflare domain ready.

Reason:

- We only need to prove Telegram webhook delivery first.
- Twilio is being saved for later.
- ngrok gets us from local code to a real bot test quickly.

When the bot becomes stable, move to Cloudflare Tunnel or a deployed server.

## Practical rule

- Local quick testing: ngrok.
- Stable staging with a real domain: Cloudflare Tunnel.
- Production: deployed app plus Cloudflare in front, or a stable Cloudflare Tunnel if that is the chosen hosting model.
