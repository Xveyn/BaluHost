"""Read-or-create the singleton AuthPolicy row (id=1)."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.auth_policy import AuthPolicy


def get_auth_policy(db: Session) -> AuthPolicy:
    policy = db.execute(select(AuthPolicy).where(AuthPolicy.id == 1)).scalar_one_or_none()
    if policy is None:
        policy = AuthPolicy(id=1)
        db.add(policy)
        db.commit()
        db.refresh(policy)
    return policy
