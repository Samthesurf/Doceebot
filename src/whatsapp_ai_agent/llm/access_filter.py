from whatsapp_ai_agent.core.permissions import Role, role_can_access


def assert_role_allowed(requester_role: Role, required_role: Role) -> None:
    if not role_can_access(requester_role, required_role):
        raise PermissionError("Requested context is outside the user's role")
