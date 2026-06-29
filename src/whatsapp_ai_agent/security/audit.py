from dataclasses import dataclass, field
from datetime import datetime

from whatsapp_ai_agent.core.timestamps import utc_now


@dataclass(frozen=True)
class AuditEvent:
    action: str
    actor_id: str | None = None
    org_id: str | None = None
    created_at: datetime = field(default_factory=utc_now)
