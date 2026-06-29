from dataclasses import dataclass


@dataclass(frozen=True)
class TenantScope:
    org_id: str
    user_id: str | None = None


def require_org_scope(scope: TenantScope) -> str:
    if not scope.org_id:
        raise PermissionError("Event has no resolved organization")
    return scope.org_id
