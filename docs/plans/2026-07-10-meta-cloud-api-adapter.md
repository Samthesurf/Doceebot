# Meta WhatsApp Cloud API Adapter Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Add a secure direct Meta WhatsApp Cloud API provider to Doceebot while preserving the existing Twilio and Telegram adapters.

**Architecture:** The Meta adapter remains isolated in `integrations/whatsapp_meta/`. It validates Meta's webhook handshake and `X-Hub-Signature-256`, normalizes each inbound Meta message into the shared `InboundEvent`, and runs the existing tenant-resolution and processing workflow in a daemon thread with a private event loop. Outbound replies use the Graph API with a server-side bearer token. The existing Twilio route remains untouched.

**Tech Stack:** Python 3.11, FastAPI, Pydantic v2, httpx, SQLAlchemy, pytest, Meta WhatsApp Cloud API.

**Security and scope constraints:**
- Never put Meta credentials, access tokens, App Secrets, or webhook verify tokens in Git.
- The repository receives placeholder names in `.env.example` only. Runtime secrets are added only to `/opt/doceebot/.env` after deployment.
- Do not migrate or configure the production phone number. Validate the adapter against Meta's test number first.
- Return HTTP 200 quickly from Meta webhooks, then run long AI processing in a daemon thread rather than FastAPI `BackgroundTasks`.
- Meta's signed raw body must be verified before JSON parsing or processing.

---

### Task 1: Update the provider contract and configuration

**Objective:** Model direct Meta Cloud API as a first-class, opt-in WhatsApp provider without weakening the existing Twilio production checks.

**Files:**
- Modify: `PRODUCT_PLAN.md`
- Modify: `src/whatsapp_ai_agent/core/events.py`
- Modify: `src/whatsapp_ai_agent/config.py`
- Modify: `.env.example`
- Test: `tests/unit/test_config.py`

**Step 1: Write failing tests**

Add tests showing that:

```python
Settings(
    app_env="production",
    app_base_url="https://example.com",
    secret_key="app-secret",
    twilio_webhook_auth_enabled=True,
    twilio_auth_token="twilio-token",
    telegram_webhook_secret_token="telegram-secret",
    meta_whatsapp_enabled=True,
    meta_webhook_auth_enabled=True,
    meta_app_secret="meta-app-secret",
    meta_webhook_verify_token="verify-token",
    meta_access_token="access-token",
    meta_phone_number_id="123",
    _env_file=None,
)
```

is valid, while each missing required Meta security value is rejected when `meta_whatsapp_enabled=True` in production.

**Step 2: Run the focused test and confirm it fails**

```bash
uv run pytest tests/unit/test_config.py -q
```

**Step 3: Implement the smallest provider model**

- Add `whatsapp_meta` to `InboundEvent.platform`.
- Add `META_WHATSAPP_ENABLED`, `META_GRAPH_API_BASE_URL`, `META_GRAPH_API_VERSION`, `META_WABA_ID`, `META_PHONE_NUMBER_ID`, `META_ACCESS_TOKEN`, `META_APP_SECRET`, `META_WEBHOOK_VERIFY_TOKEN`, and `META_WEBHOOK_AUTH_ENABLED` settings.
- Preserve the current Twilio production validation. Add Meta validation only when Meta is enabled.
- Document placeholder Meta variables in `.env.example`.
- Amend the product plan to explicitly permit a parallel, test-number-only Meta adapter and a later deliberate production cutover.

**Step 4: Re-run the focused test**

```bash
uv run pytest tests/unit/test_config.py -q
```

Expected: all config tests pass.

### Task 2: Implement Meta webhook signature and payload normalization

**Objective:** Securely verify a Meta webhook and transform text, media, and location messages into the shared event model.

**Files:**
- Create: `src/whatsapp_ai_agent/integrations/whatsapp_meta/__init__.py`
- Create: `src/whatsapp_ai_agent/integrations/whatsapp_meta/parser.py`
- Modify: `src/whatsapp_ai_agent/security/webhooks.py`
- Test: `tests/unit/test_meta_whatsapp_parser.py`
- Test: `tests/unit/test_webhook_security.py`

**Step 1: Write failing tests**

Cover:

- text message normalization;
- image, audio/voice, video, and document media metadata;
- image/document/video captions;
- location messages;
- malformed/missing message fields;
- Unix timestamp parsing;
- valid `sha256=<digest>` Meta header;
- wrong/missing signature rejection;
- development-only bypass when Meta webhook validation is explicitly disabled.

**Step 2: Run tests and confirm failure**

```bash
uv run pytest tests/unit/test_meta_whatsapp_parser.py tests/unit/test_webhook_security.py -q
```

**Step 3: Implement parsing and security**

- Use `entry[].changes[].value.messages[]` as the supported inbound-message shape.
- Ignore `statuses[]` callbacks: they report delivery state, not inbound user content.
- Use the `from` WhatsApp ID as both `platform_user_id` and `platform_chat_id` so the existing digit-normalized tenant resolver works.
- Store each Meta media object ID as `MediaRef.platform_media_id`; do not trust a URL supplied in an inbound callback.
- Verify the raw request body with HMAC-SHA256 under `META_APP_SECRET`, using a constant-time comparison.

**Step 4: Re-run focused tests**

```bash
uv run pytest tests/unit/test_meta_whatsapp_parser.py tests/unit/test_webhook_security.py -q
```

### Task 3: Implement outbound text and Meta media retrieval

**Objective:** Send direct Meta text replies and retrieve incoming media with an authenticated, two-step Graph API download flow.

**Files:**
- Create: `src/whatsapp_ai_agent/integrations/whatsapp_meta/sender.py`
- Modify: `src/whatsapp_ai_agent/media/downloader.py`
- Test: `tests/unit/test_meta_whatsapp_sender.py`
- Test: `tests/unit/test_media_downloader.py`

**Step 1: Write failing tests**

Validate that `MetaWhatsAppSender.send_text()` posts this shape to the configured Graph endpoint:

```json
{
  "messaging_product": "whatsapp",
  "recipient_type": "individual",
  "to": "<digits-only-recipient>",
  "type": "text",
  "text": {"body": "..."}
}
```

Validate `MetaMediaDownloader`:

1. `GET /<media-id>` with bearer authentication;
2. reads the returned temporary `url`, MIME type, and filename;
3. downloads that URL with bearer authentication;
4. returns the actual bytes and the best available metadata;
5. fails clearly if the media ID, token, metadata URL, or download request is unavailable.

**Step 2: Run tests and confirm failure**

```bash
uv run pytest tests/unit/test_meta_whatsapp_sender.py tests/unit/test_media_downloader.py -q
```

**Step 3: Implement minimal clients**

- Use `httpx.AsyncClient`, no additional dependency.
- Set `Authorization: Bearer <META_ACCESS_TOKEN>` on both Graph API calls.
- Construct the messages endpoint from the configurable Graph base URL, version, and phone-number ID.
- Register `whatsapp_meta` in `downloader_for_event`.

**Step 4: Re-run focused tests**

```bash
uv run pytest tests/unit/test_meta_whatsapp_sender.py tests/unit/test_media_downloader.py -q
```

### Task 4: Add a fast, signed Meta webhook route

**Objective:** Expose the Meta verification and event endpoint without blocking the FastAPI worker during AI processing.

**Files:**
- Create: `src/whatsapp_ai_agent/integrations/whatsapp_meta/webhook.py`
- Modify: `src/whatsapp_ai_agent/main.py`
- Test: `tests/unit/test_meta_whatsapp_webhook.py`

**Step 1: Write failing tests**

Cover:

- GET verification returns the raw challenge only when `hub.mode=subscribe` and the verify token matches;
- invalid verification returns 403;
- invalid POST signature returns 403;
- valid inbound message returns `{"status": "accepted"}` immediately;
- status-only callbacks return accepted without an AI job;
- a valid message is dispatched to a daemon-thread event loop and eventually sends the final response;
- the deferred function opens its own DB session;
- unresolved sender response remains consistent with the other providers.

**Step 2: Run tests and confirm failure**

```bash
uv run pytest tests/unit/test_meta_whatsapp_webhook.py -q
```

**Step 3: Implement the route**

- Register `/webhooks/meta/whatsapp`.
- GET verifies Meta's subscription challenge.
- POST reads raw bytes, verifies `X-Hub-Signature-256`, parses JSON, creates one event per `messages[]` element, and returns HTTP 200 rapidly.
- Spawn one daemon thread per inbound event, create a private asyncio event loop in that thread, open a new DB session, resolve tenant scope before any LLM call, then send the final Graph API reply.
- Never use FastAPI `BackgroundTasks` for the slow AI turn.
- Log failures without logging Meta access tokens, signatures, or bodies that could contain credentials.

**Step 4: Re-run focused tests**

```bash
uv run pytest tests/unit/test_meta_whatsapp_webhook.py -q
```

### Task 5: Review, package, and deploy safely

**Objective:** Prove direct-Meta behavior does not regress existing Doceebot channels, then deploy the endpoint without adding secrets to Git.

**Files:**
- Modify only files already covered above, plus test files.

**Step 1: Run review checks**

```bash
uv run ruff check .
uv run pytest tests/unit -q
```

**Step 2: Review the exact diff**

```bash
git diff --check
git diff --stat
git diff -- src/whatsapp_ai_agent/config.py src/whatsapp_ai_agent/security/webhooks.py src/whatsapp_ai_agent/integrations/whatsapp_meta src/whatsapp_ai_agent/media/downloader.py src/whatsapp_ai_agent/main.py
```

Confirm that no access token, App Secret, verify token, or runtime `.env` content appears.

**Step 3: Commit source changes**

```bash
git add PRODUCT_PLAN.md .env.example docs/plans/ src/whatsapp_ai_agent/ tests/
git commit -m "feat: add Meta WhatsApp Cloud API adapter"
```

**Step 4: Deploy from the source checkout**

```bash
sudo bash scripts/deploy_update_restart.sh --no-pull --run-tests
```

Confirm `/opt/doceebot/DEPLOYED_COMMIT` matches the committed source revision, then probe local and public health.

**Step 5: Configure only runtime Meta values and verify the webhook**

Add the generated App Secret, permanent system-user access token, and a long random verify token only to `/opt/doceebot/.env`. Then restart the service and configure the Meta callback URL:

```text
https://doceebot.name.ng/webhooks/meta/whatsapp
```

Verify Meta's GET challenge succeeds before subscribing the `messages` webhook field. Test the supplied Meta test number end-to-end before any production-number migration.
