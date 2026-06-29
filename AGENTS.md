# WhatsApp AI Agent Project Notes

- Use the product plan in `PRODUCT_PLAN.md` as the source of truth.
- WhatsApp is through Twilio. Do not build against direct Meta Cloud API unless the plan changes.
- Keep provider adapters separate, then normalize into shared `InboundEvent` models.
- Enforce organization and role permissions before LLM or RAG context is built.
- LLMs should return strict JSON validated by Pydantic. Document generation must be deterministic Python code.
- Do not commit real credentials. Use `.env.example` only for placeholders.
