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


class UserPublic(UserBase):
    id: str
    role: str


class UsersResponse(BaseModel):
    users: list[UserPublic]
