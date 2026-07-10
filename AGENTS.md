# WhatsApp AI Agent Project Notes

- Use the product plan in `PRODUCT_PLAN.md` as the source of truth.
- WhatsApp uses Twilio by default. A direct Meta Cloud API adapter is permitted only as a separate provider adapter, first against Meta's test number, with no production-number migration until end-to-end verification succeeds.
- Keep provider adapters separate, then normalize into shared `InboundEvent` models.
- Enforce organization and role permissions before LLM or RAG context is built.
- LLMs should return strict JSON validated by Pydantic. Document generation must be deterministic Python code.
- Do not commit real credentials. Use `.env.example` only for placeholders.
