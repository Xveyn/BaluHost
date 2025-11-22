from fastapi import APIRouter, Depends, HTTPException, status

from app.api import deps
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse
from app.schemas.user import UserPublic
from app.services import auth as auth_service
from app.services import users as user_service

router = APIRouter()


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest) -> TokenResponse:
    user_record = auth_service.authenticate_user(payload.username, payload.password)
    if not user_record:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    token = auth_service.create_access_token(user_record)
    user_public = user_service.serialize_user(user_record)
    return TokenResponse(access_token=token, user=user_public)


@router.post("/register", response_model=TokenResponse)
async def register(payload: RegisterRequest) -> TokenResponse:
    exists = user_service.get_user_by_username(payload.username)
    if exists:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User already exists")

    user_record = user_service.create_user(payload)
    token = auth_service.create_access_token(user_record)
    user_public = user_service.serialize_user(user_record)
    return TokenResponse(access_token=token, user=user_public)


@router.get("/me", response_model=UserPublic)
async def read_current_user(current_user: UserPublic = Depends(deps.get_current_user)) -> UserPublic:
    return current_user


@router.post("/logout")
async def logout() -> dict[str, str]:
    return {"message": "Logged out"}
