from pydantic import BaseModel, EmailStr


class UserBase(BaseModel):
    username: str
    email: EmailStr


class UserCreate(UserBase):
    password: str
    role: str | None = "user"


class UserUpdate(BaseModel):
    username: str | None = None
    email: EmailStr | None = None
    password: str | None = None
    role: str | None = None
    is_active: bool | None = None


class UserPublic(UserBase):
    id: int
    role: str
    is_active: bool
    created_at: str
    updated_at: str | None = None


class UsersResponse(BaseModel):
    users: list[UserPublic]
    total: int
    active: int
    inactive: int
    admins: int
