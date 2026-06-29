# WhatsApp AI Agent

A FastAPI based work logging assistant for WhatsApp and Telegram. Users send text, voice notes, images, documents, or location pins. The backend normalizes them into dated work memory, then creates summaries, DOCX reports, and XLSX work logs.

## Current scaffold

- FastAPI app with `/health`.
- Twilio WhatsApp webhook adapter at `/webhooks/twilio/whatsapp`.
- Telegram webhook adapter at `/webhooks/telegram/webhook`.
- Shared `InboundEvent`, `MediaRef`, and `LocationRef` models.
- Initial tenant, permission, database, RAG, media, worker, and document generation modules.
- Unit tests for settings, health, event timestamps, Twilio parsing, and Telegram parsing.

## Project documents

- Product plan: [`PRODUCT_PLAN.md`](PRODUCT_PLAN.md)
- Current implementation status: [`IMPLEMENTATION_STATUS.md`](IMPLEMENTATION_STATUS.md)
- Local tunnel crash course: [`docs/TUNNELS.md`](docs/TUNNELS.md)

## Local setup

```bash
uv sync
cp .env.example .env
uv run pytest
uv run uvicorn whatsapp_ai_agent.main:app --reload
```

Open `http://localhost:8000/health` to confirm the app is running.

## Local services

```bash
docker compose up -d postgres redis
```

## Required credentials before live channel testing

- Twilio Account SID.
- Twilio Auth Token.
- Twilio WhatsApp sender or Messaging Service SID.
- A public tunnel URL, for example ngrok, for local Twilio webhooks.
- Telegram BotFather token.
- Gemini API key.
- DeepSeek API key.
- Cloudflare account details for R2 and managed RAG when production storage is ready.

## Architecture reminders

- PostgreSQL is the source of truth for exact work logs and reports.
- Cloudflare AI Search or AutoRAG is secondary semantic retrieval.
- Supervisors should receive summaries by default, not raw worker chats, voice notes, or OCR dumps.
- Twilio needs a public media URL for outbound WhatsApp DOCX or XLSX delivery.
