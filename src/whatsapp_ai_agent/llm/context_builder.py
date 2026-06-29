from dataclasses import dataclass

from whatsapp_ai_agent.core.permissions import Role


@dataclass(frozen=True)
class ContextRequest:
    org_id: str
    user_id: str
    role: Role
    query: str


def build_permission_gated_context(request: ContextRequest) -> list[str]:
    # Retrieval will be implemented after tenant scoped repositories exist.
    return []
