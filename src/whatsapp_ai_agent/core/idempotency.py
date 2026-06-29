from whatsapp_ai_agent.core.events import InboundEvent


def inbound_event_key(event: InboundEvent) -> str:
    return f"{event.platform}:{event.platform_message_id}"
