# Doceebot

**A chat-first work memory system for people who do real work away from a desk.**

Doceebot lets a worker send a text, voice note, image, document, or location through a familiar chat channel. The system turns that message into structured work memory, keeps it inside the right organization, and makes it useful later through summaries, reports, document updates, and search.

The goal is to let the work happen where the worker already is, then give supervisors and teams something more useful than a pile of raw chats.

## Where the project is now

This repository has moved beyond the original webhook scaffold.

- Twilio WhatsApp and Telegram adapters feed a shared inbound-event model.
- The direct Meta WhatsApp Cloud API adapter has passed a real test-number conversation end to end.
- Text, voice, image, document, and location messages have channel-specific parsing paths.
- Tenant and permission checks happen before AI context and retrieval are built.
- PostgreSQL and Alembic hold durable work records and message audit data.
- Gemini handles multimodal extraction, while DeepSeek handles structured work reasoning.
- Cloudflare R2 and AI Search support document storage and organization-scoped retrieval.
- Deterministic Python generators create DOCX reports and XLSX work logs.
- The dashboard API and frontend provide an admin view into organizations, documents, logs, escalations, and token usage.

The Meta integration is currently a test-account provider. It sits beside Twilio, not in place of it. Production-number migration is deliberately a separate decision.

## The core loop

```text
Worker sends a chat message
        ↓
Channel adapter normalizes it
        ↓
Media is downloaded and extracted when needed
        ↓
Tenant and permission scope is resolved
        ↓
AI turns the message into structured work data
        ↓
PostgreSQL stores the durable record
        ↓
Doceebot answers, updates a document, or generates a report
```

That order matters. The system should know which organization and permissions apply before it builds the prompt or retrieves private context.

## Channels

| Channel | Role in the codebase | Current position |
| --- | --- | --- |
| Twilio WhatsApp | Existing WhatsApp provider | Kept as the default adapter |
| Telegram | Chat and file channel | Separate adapter using the Telegram Bot API |
| Meta Cloud API | Direct WhatsApp provider | Test-number conversation verified end to end |

The adapters stay separate, then converge on shared `InboundEvent`, media, tenant, workflow, and document interfaces.

## What makes the backend interesting

### A real webhook is not the whole product

The webhook routes are intentionally thin. They authenticate the request, parse the payload, claim the event, acknowledge quickly, and move the slow AI work into a private deferred loop. A slow model call should not block the next webhook or make Meta retry the same message.

### Privacy is part of the workflow

Organization scope and permissions are checked before LLM or RAG context is assembled. Raw worker chats, voice notes, and OCR dumps are not automatically treated as supervisor reports.

### Documents are generated deterministically

The model returns validated structured data. Python code creates the DOCX or XLSX file. This keeps the file format, tables, and formulas under application control rather than asking a model to write arbitrary document code.

### Meta has its own operational traps

The direct Meta path needed more than a token and a webhook URL. The Developer App had to be explicitly subscribed to the correct WABA. The Meta dashboard also sends synthetic webhook-test events that are not the same as a real WhatsApp chat. The complete setup and troubleshooting story is documented in [`docs/META_WHATSAPP_CLOUD_API_RUNBOOK.md`](docs/META_WHATSAPP_CLOUD_API_RUNBOOK.md).

## Repository map

```text
src/whatsapp_ai_agent/
├── api/                 Dashboard and document APIs
├── core/                Shared event and application contracts
├── db/                  SQLAlchemy models, repositories, and sessions
├── integrations/        Twilio, Telegram, and direct Meta adapters
├── llm/                 Gemini, DeepSeek, prompts, schemas, and access filters
├── media/               Download, storage, image, and audio handling
├── memory/              Tenant scope, conversation commands, and work memory
├── rag/                 Cloudflare AI Search and organization metadata
└── workflows/           Inbound processing and report/document actions

dashboard/               React/Vite admin interface
alembic/                  Database migrations
docs/                     Deployment and integration runbooks
tests/                    Unit and integration-facing checks
```

## Local development

The backend uses Python 3.11+, `uv`, FastAPI, and PostgreSQL.

```bash
uv sync
cp .env.example .env
uv run alembic upgrade head
uv run pytest tests/unit -q
uv run ruff check .
uv run uvicorn whatsapp_ai_agent.main:app --reload
```

Then open:

```text
http://localhost:8000/health
```

PostgreSQL and Redis can be started through Docker Compose when preferred. The local environment also supports native PostgreSQL development.

## Deployment shape

The source checkout is:

```text
/root/Doceebot
```

The live runtime is:

```text
/opt/doceebot
```

Deploy from the source checkout:

```bash
bash scripts/deploy_update_restart.sh --no-pull --run-tests
```

The backend deploy and the dashboard deploy are separate operations. The dashboard is deployed with Wrangler from `dashboard/`.

## What comes next

Production onboarding with a dedicated Doceebot phone number, a production WABA(Whatsapp Business Account), approved templates, and a deliberate decision about how Twilio remains in the architecture.

The other work is the unglamorous part that makes the product trustworthy: stronger tenant onboarding, richer work corrections, supervisor summaries, media validation, and more document workflows.

Doceebot is still evolving, but the direction is clear: chat in, structured organizational memory out.
