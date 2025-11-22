from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Dict, Iterable, Optional
from uuid import uuid4

from passlib.context import CryptContext

from app.core.config import Settings
from app.schemas.user import UserCreate, UserPublic, UserUpdate

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


@dataclass
class UserRecord:
    id: str
    username: str
    email: str
    role: str
    password_hash: str


_store: Dict[str, UserRecord] = {}


def ensure_admin_user(settings: Settings) -> None:
    existing = get_user_by_username(settings.admin_username)
    if existing:
        return

    payload = UserCreate(
        username=settings.admin_username,
        email=settings.admin_email,
        password=settings.admin_password,
        role=settings.admin_role,
    )
    create_user(payload)


def list_users() -> Iterable[UserRecord]:
    return _store.values()


def get_user(user_id: str) -> Optional[UserRecord]:
    return _store.get(user_id)


def get_user_by_username(username: str) -> Optional[UserRecord]:
    return next((user for user in _store.values() if user.username == username), None)


def create_user(payload: UserCreate) -> UserRecord:
    user_id = str(uuid4())
    password_hash = pwd_context.hash(payload.password)
    record = UserRecord(
        id=user_id,
        username=payload.username,
        email=payload.email,
        role=payload.role or "user",
        password_hash=password_hash,
    )
    _store[user_id] = record
    return record


def update_user(user_id: str, payload: UserUpdate) -> Optional[UserRecord]:
    record = _store.get(user_id)
    if not record:
        return None

    if payload.username:
        record.username = payload.username
    if payload.email:
        record.email = payload.email
    if payload.role:
        record.role = payload.role
    if payload.password:
        record.password_hash = pwd_context.hash(payload.password)
    return record


def delete_user(user_id: str) -> bool:
    return _store.pop(user_id, None) is not None


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def serialize_user(record: UserRecord) -> UserPublic:
    data = asdict(record)
    data.pop("password_hash", None)
    return UserPublic(**data)
