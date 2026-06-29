from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True)
class ActiveSiteSession:
    site_name: str
    expires_at: datetime

    def is_active(self, now: datetime) -> bool:
        return now <= self.expires_at


def new_active_site_session(site_name: str, now: datetime, ttl_hours: int) -> ActiveSiteSession:
    return ActiveSiteSession(site_name=site_name, expires_at=now + timedelta(hours=ttl_hours))
