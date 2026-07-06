# Doceebot Dashboard

A React, Vite, and Cloudflare Workers dashboard for Doceebot operations.

## Live routes

- `/dashboard` - Firebase-protected operations dashboard.
- `/logs` - Firebase-protected log viewer with an additional logs password gate.

## What the dashboard shows

- Organization visibility: tenants, members, active sessions, documents, and work logs.
- Document inventory: uploaded/generated DOCX/XLSX files, status, owners, tags, sizes, and update counts.
- Chatbot UX analytics: unconfirmed draft rate, correction rate, fallback rate, messages per confirmed log, media processing events, and average session length.
- Developer escalations from `report ...`: report text, status, linked conversation counts, and delivery errors.
- Conversation logs: recent session turns and metadata behind the extra logs-password gate.

## Local development

```bash
cd dashboard
npm install
cp .env.example .env.local
npm run dev
```

The Firebase values are public web-app configuration, but keep real local env files uncommitted.

## Production deployment

```bash
cd dashboard
npm run build
wrangler deploy
```

The app is served by `doceebot-dashboard` on the `doceebot.name.ng/dashboard*` and `doceebot.name.ng/logs*` Cloudflare routes.
