from enum import StrEnum


class Role(StrEnum):
    WORKER = "worker"
    SUPERVISOR = "supervisor"
    MANAGER = "manager"
    ORG_ADMIN = "org_admin"


class Visibility(StrEnum):
    PRIVATE = "private"
    WORKER_VISIBLE = "worker_visible"
    SUPERVISOR_SUMMARY = "supervisor_summary"
    MANAGEMENT = "management"


ROLE_RANK: dict[Role, int] = {
    Role.WORKER: 10,
    Role.SUPERVISOR: 20,
    Role.MANAGER: 30,
    Role.ORG_ADMIN: 40,
}


def role_can_access(requester_role: Role, required_role: Role) -> bool:
    return ROLE_RANK[requester_role] >= ROLE_RANK[required_role]
