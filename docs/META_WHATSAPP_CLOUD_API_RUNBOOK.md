# Doceebot Meta WhatsApp Cloud API Runbook

> **Purpose:** This is the complete, screen-by-screen record of how Doceebot was connected to Meta WhatsApp Cloud API, why the first tests were misleading, how the missing WABA subscription was found and fixed, and how to repeat the process without guessing.
>
> **Status:** Test-account end-to-end messaging passed on 2026-07-10. A real allow-listed WhatsApp number sent a message to Meta's Test Number and received a Doceebot AI reply.
>
> **Scope:** This runbook covers the direct Meta provider (`whatsapp_meta`). It does not replace Twilio or Telegram. Keep those integrations intact until a separate production cutover has passed.

---

## 1. The result to aim for

A working test flow is:

```text
Personal WhatsApp test recipient
        ↓ sends a normal chat message
Meta Test Number
        ↓
Test WhatsApp Business Account (Test WABA)
        ↓
Doceebot Meta Developer App, subscribed to the WABA
        ↓ signed HTTPS webhook
https://doceebot.name.ng/webhooks/meta/whatsapp
        ↓
Doceebot tenant resolution and AI workflow
        ↓ Graph API reply, using the permanent system-user token
Personal WhatsApp test recipient
```

A successful response from Doceebot proves all of these were correct at the same time:

- the test recipient was allowed;
- the Test Number belonged to the configured WABA;
- the correct Developer App was subscribed to that WABA;
- the callback URL and `messages` field subscription worked;
- the webhook signature passed;
- the permanent token could send through the configured Phone Number ID;
- Doceebot could resolve and process the incoming event.

---

## 2. Read this before touching the Meta dashboard

Meta splits WhatsApp setup across several pages. Most of the stress in this rollout came from using the right instruction on the wrong Meta page.

| Meta area | Exact use | What it is **not** for |
| --- | --- | --- |
| **Meta Developer App Dashboard** | Test Number, test recipient list, temporary console token, webhook configuration | Billing or production-number registration |
| **WhatsApp Manager** | WABA administration, connected phone numbers, quality, later billing | Adding a test recipient |
| **Meta Business Settings** | System user, asset assignment, permanent token | Webhook callback URL |
| **Doceebot server `.env`** | Runtime-only Meta IDs and secrets | Any Git-tracked configuration |

### The labels that matter

On the current Meta UI, the correct test path is usually:

```text
Meta for Developers
→ select the Doceebot app
→ Dashboard
→ Customize the "Connect with customers through WhatsApp" use case
→ Basic setup
→ Step 1. Try it out
```

This is the page that eventually shows:

```text
From: [Meta Test Number]
To:   [allow-listed personal recipient]
```

Do **not** confuse it with these pages:

| Visible label | Meaning | Use during test pilot? |
| --- | --- | --- |
| `Step 2. Production setup` | Real production WABA and phone-number onboarding | No |
| `Add phone number` in WhatsApp Manager | Register a real business number, potentially involving billing | No |
| `Add payment method` | Production billing setup | No |
| `Testing` in the general app sidebar | Generic Meta app testing, not WhatsApp recipient setup | No |
| `Send a message to your server` | Synthetic webhook test only | Never use as an end-to-end chat test |

---

## 3. Key terms, in plain English

| Term | Meaning | Doceebot example |
| --- | --- | --- |
| **Meta Business Portfolio** | The parent business container in Meta Business Manager | Surf Services |
| **WABA** | WhatsApp Business Account. A Meta container holding phone numbers, templates, billing, quality, and app subscriptions | Test WABA now, production WABA later |
| **Business phone number** | The WhatsApp number Meta sends from and receives on | Meta Test Number now, dedicated Doceebot SIM later |
| **Phone Number ID** | Meta's API identifier for one business phone number | Used in `POST /{PHONE_NUMBER_ID}/messages` |
| **Developer App** | The Meta application that owns the webhook configuration and API integration | Doceebot |
| **System user** | A non-human Meta Business identity used by the server | Doceebot Meta API system user |
| **Permanent system-user token** | Long-lived server credential generated for a system user and app | Stored only in deployed `.env` |
| **Test recipient** | A personal WhatsApp number allow-listed for sandbox messaging | The test operator's personal WhatsApp number |

The most important relationship is:

```text
Business Portfolio
  └── WABA
       ├── Business Phone Number
       └── Subscribed Developer App
            └── Webhook callback URL
```

The phone number, WABA, Developer App, and permanent token are related, but they are not the same thing.

---

## 4. What had to be built on the Doceebot side

Meta had no direct adapter in Doceebot originally. Existing WhatsApp support was Twilio-based, so a separate provider was implemented instead of replacing Twilio.

### 4.1 Provider architecture

The implementation lives here:

```text
src/whatsapp_ai_agent/integrations/whatsapp_meta/
├── client.py       Graph URL and Bearer-header helpers
├── parser.py       Meta webhook payload normalization
├── sender.py       outbound Graph API messages
└── webhook.py      GET verification, POST authentication, dispatch
```

The public callback route is:

```text
GET  /webhooks/meta/whatsapp
POST /webhooks/meta/whatsapp
```

The provider normalizes Meta events into the same shared `InboundEvent` contract used by Twilio and Telegram. This preserves tenant resolution, document/work logging, media handling, and AI workflow behaviour.

### 4.2 Security rules implemented

1. **GET verification**
   - Meta sends `hub.mode`, `hub.verify_token`, and `hub.challenge`.
   - Doceebot checks that `hub.mode=subscribe` and compares the verify token with a constant-time comparison.
   - On success, Doceebot returns the raw challenge as `text/plain`.

2. **POST authentication**
   - Meta sends `X-Hub-Signature-256`.
   - Doceebot validates HMAC-SHA256 over the **raw request bytes** with `META_APP_SECRET`.
   - Parsed or re-serialized JSON must never be used for signature verification because changing whitespace or key order changes the signed data.

3. **Secret boundary**
   - Real credentials belong only in `/opt/doceebot/.env`.
   - `.env.example` contains placeholders only.
   - Never paste the permanent token, App Secret, verify token, or runtime `.env` into chat, Git, screenshots, tests, or logs.

### 4.3 Reliability rules implemented

- Meta webhook requests receive a fast `200 {"status":"accepted"}` acknowledgement.
- AI work runs later in a daemon thread with its own event loop and private database session.
- Meta retry protection uses a durable database claim keyed by `(platform, platform_message_id)`, not an in-memory lock.
- Delivery and read status callbacks are acknowledged but do not start an AI turn.
- Media download uses Meta's authenticated two-request flow: resolve media ID, then download with Bearer authentication.

### 4.4 Code and deployment evidence

| Commit | Purpose |
| --- | --- |
| `d9f2878` | Added the direct Meta WhatsApp Cloud API adapter, webhook security, parser, sender, media support, and durable duplicate-event guard |
| `d4ed172` | Added safe Meta Graph API failure diagnostics without exposing credentials |

Before deployment, the focused Meta tests, full unit suite, Ruff, and `git diff --check` were run. The source was deployed with:

```bash
cd /root/Doceebot
bash scripts/deploy_update_restart.sh --no-pull --run-tests
```

The deployed runtime is `/opt/doceebot`; never edit only that directory because the deploy script syncs from `/root/Doceebot` and removes runtime-only source changes.

---

## 5. Test-account setup, exact order

Follow this order. Do not jump to Production Setup while validating the sandbox.

### Step 1: Open the correct Meta page

1. Open [Meta for Developers](https://developers.facebook.com/apps/).
2. Select the **Doceebot** app.
3. From the Dashboard, select:

   ```text
   Customize the "Connect with customers through WhatsApp" use case
   ```

4. In the left-side setup list, select:

   ```text
   Basic setup
   → Step 1. Try it out
   ```

If the page looks like it has forgotten the previous test, do not panic. Meta often shows:

```text
Temporary access token: Not generated yet
```

That only means the browser console's temporary token is absent or expired. It does **not** invalidate the server's permanent system-user token.

### Step 2: Identify the test phone number and add the test recipient

On `Step 1. Try it out`, find the send-test area:

```text
From: [Meta Test Number]
To:   [recipient phone number]
```

1. Keep the Meta-provided **From** number unchanged.
2. Under **To**, select one of:

   ```text
   Add phone number
   Manage phone number list
   Add recipient
   ```

3. Add the personal WhatsApp number that will send the real test message.
4. Enter the number in full international format, for example:

   ```text
   +234XXXXXXXXXX
   ```

5. Complete the OTP verification Meta sends.
6. Confirm the number is visible and verified in the recipient list.

This test recipient list is sandbox-only. It is not the page for registering Doceebot's future real phone number.

### Step 3: Create the permanent server credential correctly

The temporary token on `Step 1. Try it out` is useful only for a quick browser-console experiment. Doceebot must use a permanent system-user token.

In Meta Business Settings:

```text
Business Settings
→ Users
→ System Users
```

1. Create or open the dedicated `Doceebot Meta API` system user.
2. Use **Add assets** before generating the token.
3. Assign both:
   - the **Doceebot Developer App**;
   - the **Test WABA**.
4. Give the required access level Meta offers for this integration.
5. Generate a token for the **Doceebot app**, with at least:

   ```text
   business_management
   whatsapp_business_management
   whatsapp_business_messaging
   ```

6. Store the token privately. Do not put it in Git or chat.

> **Why asset assignment must come first:** a token generated before the app and WABA are assigned can authenticate but still be missing the app-to-WABA relationship needed for real Cloud API operations.

### Step 4: Obtain the App Secret

In the Doceebot Developer App Dashboard:

```text
App settings
→ Basic
→ App secret
```

Store it privately. It authenticates incoming Meta webhook POSTs. It is different from the permanent token and different from the webhook verify token.

### Step 5: Create the webhook verify token

This token is invented by the Doceebot operator. Meta does not generate it.

Generate it privately, for example:

```bash
openssl rand -hex 32
```

Store the exact value in server runtime configuration and paste the exact same value into Meta's callback verification form.

### Step 6: Configure server runtime settings

Only in `/opt/doceebot/.env`, set non-placeholder values:

```dotenv
META_WHATSAPP_ENABLED=true
META_GRAPH_API_BASE_URL=https://graph.facebook.com
META_GRAPH_API_VERSION=v23.0
META_WABA_ID=<test-waba-id>
META_PHONE_NUMBER_ID=<meta-test-phone-number-id>
META_ACCESS_TOKEN=<permanent-system-user-token>
META_APP_SECRET=<meta-app-secret>
META_WEBHOOK_VERIFY_TOKEN=<random-private-string>
META_WEBHOOK_AUTH_ENABLED=true
```

Restart the service after the secure runtime update:

```bash
systemctl restart doceebot
systemctl is-active doceebot
```

Expected result:

```text
active
```

### Step 7: Configure the callback in Meta

Return to the Doceebot Developer App, in the WhatsApp webhook configuration area. Depending on Meta's current UI revision, it may be called `Configuration` or `Webhooks`.

Set:

```text
Callback URL:
https://doceebot.name.ng/webhooks/meta/whatsapp

Verify token:
[the exact private META_WEBHOOK_VERIFY_TOKEN value]
```

Click **Verify and save**.

Then subscribe to the field:

```text
messages
```

The callback verification is complete only when Meta's GET request receives the challenge response. The `messages` field subscription is what asks Meta to deliver WhatsApp events.

### Step 8: Confirm the phone number is connected, but do not use this page for recipients

To inspect the Test Number:

```text
WhatsApp Manager
→ Account tools
→ Phone numbers
```

The Test Number should show a status such as:

```text
Connected
```

This page can show a payment warning and an **Add phone number** button. During the sandbox phase:

- do not add payment because of that warning;
- do not register a production number there;
- do not expect to find the test recipient list there.

The page confirms the WABA phone-number asset. The Developer App's `From` and `To` page controls sandbox recipients.

---

## 6. The WABA subscription check, the missing connection that fixed real messaging

This was the decisive operational fix.

### 6.1 What was wrong

The Test WABA had a Meta-owned internal app subscribed:

```text
WA DevX Webhook Events 1P App
```

But it did not list the actual **Doceebot** Developer App.

That created an incomplete setup:

```text
Test WABA
  ├── Meta internal test app
  └── no confirmed Doceebot app subscription
```

The Meta setup interface could still appear functional, and a synthetic dashboard test could still call the webhook. However, the real Doceebot app had not been explicitly connected to the WABA's event stream.

### 6.2 How to inspect WABA subscriptions safely

Run this only in a secure shell where the environment values are already present. Never paste a real token into a document or chat.

```bash
curl --silent --show-error --fail \
  "https://graph.facebook.com/${META_GRAPH_API_VERSION}/${META_WABA_ID}/subscribed_apps" \
  -H "Authorization: Bearer ${META_ACCESS_TOKEN}"
```

The result is a `data` array. The intended Developer App must appear by name.

A Meta internal testing app may appear too. That is normal. The problem is when the intended app, such as `Doceebot`, is absent.

Also verify the configured number belongs to the WABA:

```bash
curl --silent --show-error --fail \
  "https://graph.facebook.com/${META_GRAPH_API_VERSION}/${META_WABA_ID}/phone_numbers?fields=id,verified_name,quality_rating,code_verification_status" \
  -H "Authorization: Bearer ${META_ACCESS_TOKEN}"
```

Check IDs privately. Do not include the token in logs or screenshots.

### 6.3 Subscribe the correct app to the WABA

If `Doceebot` is absent from `subscribed_apps`, use the permanent token that was generated for the Doceebot app and correctly assigned to the WABA:

```bash
curl --silent --show-error --fail \
  -X POST \
  "https://graph.facebook.com/${META_GRAPH_API_VERSION}/${META_WABA_ID}/subscribed_apps" \
  -H "Authorization: Bearer ${META_ACCESS_TOKEN}"
```

Expected response:

```json
{"success": true}
```

Run the GET probe again. The expected state is now conceptually:

```text
Test WABA
  ├── Doceebot
  └── WA DevX Webhook Events 1P App
```

### 6.4 Why the POST worked

The permanent system-user token was created for the Doceebot app. Calling:

```text
POST /{WABA_ID}/subscribed_apps
```

tells Meta to subscribe the app associated with that credential to the specified WABA.

This is distinct from:

- assigning an asset to a system user;
- generating a permanent token;
- configuring a webhook URL;
- registering a phone number;
- adding a test recipient.

All of those may be correct while the app-to-WABA subscription is still missing.

---

## 7. The synthetic webhook-test trap

This was the main source of false signals during the rollout.

### What Meta's dashboard test does

The Meta dashboard action that says something like:

```text
Send a message to your server
```

can send a synthetic webhook payload from a Meta-owned test identity. It is not necessarily a real WhatsApp chat from the personal test recipient.

Doceebot correctly sees such a payload as an inbound message and, by design, attempts to reply to its `messages[0].from` value.

If that synthetic sender is not in the sandbox recipient allow-list, Meta returns:

```text
(#131030) Recipient phone number not in allowed list
```

That does **not** prove your real personal number is missing from the recipient list.

### The exact diagnostic rule

Before changing any recipient, token, payment, or production setting, determine which number Doceebot tried to answer:

```text
incoming payload messages[0].from
```

| Failed reply target | Meaning | Correct action |
| --- | --- | --- |
| Meta synthetic test sender | Dashboard webhook test, not a real chat | Ignore the reply failure and run a real WhatsApp test |
| Allow-listed personal number | Real chat failure | Compare normalized digits, recipient verification, WABA subscription, and app/token assets |

### The only valid end-to-end test

1. Open WhatsApp on the allow-listed personal `To` number.
2. Send an ordinary new message to the exact Meta Test Number shown under `From`.
3. Do **not** click Meta's synthetic “send to server” button.
4. Confirm the WhatsApp chat actually sends from the personal account.
5. Check Doceebot logs for a signed `POST /webhooks/meta/whatsapp` whose sender is the personal number.
6. Wait for Doceebot's reply in the same WhatsApp chat.

The successful test on 2026-07-10 followed this exact path.

---

## 8. Troubleshooting table

| Symptom | Most likely cause | Correct next check | Do not do |
| --- | --- | --- | --- |
| Meta cannot verify callback URL | Wrong callback URL or wrong verify token | Confirm exact URL and `META_WEBHOOK_VERIFY_TOKEN`; inspect GET response | Do not regenerate the App Secret |
| GET verification gets `403 Invalid Meta webhook token` | Verify token mismatch or placeholder value | Check runtime `.env` and Meta form match exactly | Do not use the App Secret as the verify token |
| POST gets `403 Invalid Meta signature` | Wrong App Secret or raw body was altered before HMAC validation | Check `META_APP_SECRET`, `X-Hub-Signature-256`, and raw-byte validation | Do not disable webhook authentication in production |
| Meta test page sends a sample to phone but Doceebot does not reply | Browser-console test does not prove server flow | Check permanent token, callback, `messages`, WABA subscription | Do not replace permanent token with temporary token |
| `#131030 Recipient phone number not in allowed list` | Often the synthetic Meta dashboard sender, or a digit mismatch on a real recipient | Identify the exact incoming `from` number first | Do not add a production number or payment method as a response |
| Personal recipient is visibly listed but real messages do not reach Doceebot | Developer App may not be subscribed to the WABA | `GET /{WABA_ID}/subscribed_apps` and ensure Doceebot appears | Do not assume the generic Meta internal app is Doceebot |
| WhatsApp Manager shows `Connected` but browser test screen looks empty | Different Meta surfaces show different state | Return to Developer App `Step 1. Try it out` for `From`/`To` recipients | Do not register a new phone number during testing |
| Meta screen asks for payment to add a number | You are on production phone management | Return to test recipient list if still testing | Do not pay just to solve a sandbox `131030` error |
| User message is accepted but comes twice | Meta retry or duplicate delivery | Verify durable `(platform, platform_message_id)` claim logic | Do not remove duplicate protection |
| Outbound Graph API is `400` with unknown cause | Insufficient sanitized error diagnostics | Log only status, code, subcode, message, detail, trace ID | Never log Authorization headers or raw access tokens |

---

## 9. Evidence that the test integration is complete

The live verification sequence passed all of the following:

```text
1. Meta callback GET verification succeeded.
2. The `messages` webhook field was subscribed.
3. Doceebot received signed Meta POST callbacks and returned HTTP 200 quickly.
4. The intended Doceebot app was explicitly subscribed to the Test WABA.
5. The actual personal WhatsApp test recipient sent a real chat to the Test Number.
6. Doceebot persisted the real inbound event.
7. Doceebot processed it through the AI workflow.
8. Meta accepted the outbound reply with no Graph API failure.
9. The personal WhatsApp account received the Doceebot response.
```

The response received by the test user was the normal Doceebot work-recording/document-update greeting. That is proof of the real Doceebot workflow, not merely a Meta dashboard test.

---

## 10. Production graduation plan, after obtaining a dedicated Doceebot SIM

### Recommended number strategy

Use a dedicated mobile SIM owned only by Doceebot.

It should:

- receive SMS and voice OTPs;
- be retained by the business long-term;
- preferably not already be registered to WhatsApp;
- be clearly separate from personal, Twilio, or human-operated business conversations.

A normal new SIM does not need to be a pre-existing WhatsApp Business number. Meta registers it as a business phone number during production onboarding.

### What to reuse

Reuse:

```text
Surf Services Meta Business Portfolio
Doceebot Meta Developer App
Doceebot server and webhook URL
```

Do not create another Meta Business Portfolio merely because the phone number is new.

### What to create or select

Use a **real production WABA**, not the generated Test WABA.

Recommended organization:

```text
Surf Services Meta Business Portfolio
├── Existing human-operated WhatsApp resources, unchanged
├── Test WABA
│   └── Meta Test Number
└── Doceebot Production WABA
    └── Dedicated Doceebot SIM
```

A WABA can hold multiple numbers, but a separate Doceebot production WABA keeps templates, quality, billing, and operational identity isolated.

### Production sequence

1. Obtain the dedicated SIM and confirm it can receive international SMS or voice OTPs.
2. In Meta's **Production setup**, create or select the production WABA under Surf Services.
3. Register the new SIM, verify ownership by OTP, and choose the display name and category.
4. Set Meta's required six-digit two-step-verification PIN.
5. Add payment/billing as Meta requires for production messaging.
6. Start or complete business verification as Meta requires for the intended production capabilities.
7. Assign the Doceebot Developer App and Doceebot system user to the production WABA.
8. Update only the runtime IDs in `/opt/doceebot/.env`:

   ```dotenv
   META_WABA_ID=<production-waba-id>
   META_PHONE_NUMBER_ID=<production-phone-number-id>
   ```

9. Verify that the permanent token still has access to the production WABA. Do not assume. Asset assignment may be needed.
10. Run:

    ```text
    POST /{PRODUCTION_WABA_ID}/subscribed_apps
    ```

    and verify `GET /{PRODUCTION_WABA_ID}/subscribed_apps` lists `Doceebot`.

11. Confirm callback URL and `messages` subscription, then put the app in Live mode when Meta's requirements are complete.
12. Run a real-user controlled test before announcing the public number.
13. Leave Twilio untouched until the production direct-Meta number has passed this test.

### Public messaging rules

After the app is Live and the production number is connected:

```text
Anyone can initiate a WhatsApp chat with the Doceebot number.
```

Doceebot can send normal free-text replies during the user-initiated 24-hour customer-service window. Outside that window, Meta requires an approved template and appropriate recipient opt-in for business-initiated messaging.

### Existing-number warning

Meta's current business-phone documentation says a number already in WhatsApp Messenger cannot be directly registered for Cloud API unless the existing WhatsApp account is deleted first. Never migrate a personal number casually.

An existing WhatsApp Business App number may have a separate Meta Coexistence onboarding option, but eligibility is account-specific. Treat it as optional only when Meta explicitly offers it. Do not assume ordinary WhatsApp Messenger numbers qualify.

Official Meta reference: [Business phone numbers](https://developers.facebook.com/docs/whatsapp/cloud-api/phone-numbers).

---

## 11. Incident chronology: what happened, why it failed, and what fixed it

This is the actual sequence that led from no direct Meta integration to the first successful real reply.

| Phase | Observation | Correct conclusion | Action taken | Result |
| --- | --- | --- | --- | --- |
| 1. Baseline | Doceebot supported Twilio WhatsApp and Telegram, but no direct Meta Cloud API channel | A separate adapter was required, not a Twilio configuration change | Added `whatsapp_meta` as an isolated provider | Twilio and Telegram stayed untouched |
| 2. Secure adapter | Meta needs a verification GET and signed POST webhook, while replies use Graph API | A simple inbound endpoint was not enough | Added raw-body HMAC validation, parser, sender, media retrieval, asynchronous processing, and duplicate-event claims | The server could safely receive and send direct Meta messages |
| 3. Runtime setup | The source repository cannot contain real Meta secrets | Code deployment alone would remain disabled | The operator stored permanent credentials only in `/opt/doceebot/.env` and restarted the service | The public route became live and protected |
| 4. Callback setup | Meta verified the callback URL and the `messages` field was subscribed | The callback URL itself was correct | Kept `https://doceebot.name.ng/webhooks/meta/whatsapp` and enabled `messages` | Meta could call Doceebot |
| 5. First apparent failure | A webhook reached Doceebot, AI processing ran, and Graph API returned `#131030` | It looked like the personal recipient was not allowed | Added safe Graph error diagnostics rather than guessing or changing production settings | The exact Meta error became visible without leaking secrets |
| 6. Recipient-list confusion | The real personal number was visibly verified in the Developer App's `To` list | The recipient list was not actually the failed target | Inspected the persisted incoming event's `messages[0].from` value | It was Meta's synthetic dashboard-test sender, not the personal test number |
| 7. Missing WABA connection | `GET /{WABA_ID}/subscribed_apps` listed only `WA DevX Webhook Events 1P App` | Meta's internal setup app was connected, but Doceebot was not confirmed as a WABA subscriber | Called `POST /{WABA_ID}/subscribed_apps` using the Doceebot permanent system-user token | Meta returned `success=true`; a new GET listed `Doceebot` and the internal app |
| 8. Valid end-to-end test | The allow-listed personal number sent an ordinary WhatsApp message to the exact Meta Test Number | This was the first real chat test, unlike Meta's synthetic dashboard event | Observed the signed POST, AI processing, and outbound send | The personal WhatsApp account received Doceebot's reply |

### The root cause in one diagram

Before the corrective Graph API subscription:

```text
Personal test recipient
    ↓
Meta Test Number → Test WABA → Meta internal test app
                                  └── synthetic dashboard test could reach the webhook

Doceebot app was not confirmed in the WABA subscription list.
```

After the corrective Graph API subscription:

```text
Personal test recipient
    ↓
Meta Test Number → Test WABA → Doceebot app → Doceebot webhook → AI reply
                         └── Meta internal test app remains present for Meta tooling
```

The `#131030` failure and the WABA subscription problem were related to the confusing test environment, but they were not the same error:

- `#131030` happened because Doceebot tried to answer Meta's synthetic test sender, which was not an allowed recipient.
- The missing `Doceebot` entry in `subscribed_apps` prevented confidence that real WABA traffic was routed through the intended app connection.
- A real chat from the allow-listed personal number, after Doceebot was subscribed to the WABA, proved the final path worked.

---

## 12. Pre-flight checklist for any future Meta setup

### Dashboard and assets

- [ ] Correct Developer App selected.
- [ ] Correct WABA selected.
- [ ] Configured Phone Number ID belongs to that WABA.
- [ ] System user has the Developer App and WABA assets assigned before token generation.
- [ ] Permanent token includes WhatsApp business management and messaging permissions.
- [ ] Developer App appears in `GET /{WABA_ID}/subscribed_apps`.

### Webhook security

- [ ] `META_WHATSAPP_ENABLED=true` only after real runtime configuration exists.
- [ ] Callback is `https://doceebot.name.ng/webhooks/meta/whatsapp`.
- [ ] GET verification succeeds with the private verify token.
- [ ] `messages` webhook field is subscribed.
- [ ] POST HMAC validation is enabled in production.

### Test flow

- [ ] Personal test recipient is verified in Developer App `From`/`To` list.
- [ ] Test is sent from WhatsApp, not the Meta synthetic-server-test button.
- [ ] Latest inbound sender matches the actual personal test number.
- [ ] Reply reaches the same personal WhatsApp chat.
- [ ] Meta Graph failures are logged safely, without secrets.

### Production safety

- [ ] Test WABA and production WABA are distinct.
- [ ] Dedicated production SIM is owned and OTP-capable.
- [ ] No personal or Twilio number is migrated without an explicit cutover plan.
- [ ] Production WABA has Doceebot subscribed through `subscribed_apps`.
- [ ] Twilio remains unchanged until direct Meta passes real-user validation.

---

## 13. The one-sentence lesson

> A configured phone number, a webhook URL, and a valid token are not enough by themselves. For real Meta WhatsApp Cloud API traffic, the correct Developer App must also be explicitly subscribed to the correct WABA, and end-to-end tests must come from a real allow-listed WhatsApp chat, not Meta's synthetic dashboard event.
