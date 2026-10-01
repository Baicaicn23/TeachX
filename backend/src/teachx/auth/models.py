from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class UserRecord:
    id: str
    username: str
    role: str
    created_at: float
    last_login_at: float | None = None

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


LOCAL_USER = UserRecord(
    id="",
    username="Local learner",
    role="admin",
    created_at=0.0,
)
