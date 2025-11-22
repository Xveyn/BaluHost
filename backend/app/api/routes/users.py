from fastapi import APIRouter, Depends, HTTPException, status

from app.api import deps
from app.schemas.user import UserCreate, UserPublic, UserUpdate, UsersResponse
from app.services import users as user_service

router = APIRouter()


@router.get("/", response_model=UsersResponse)
async def list_users(_: UserPublic = Depends(deps.get_current_admin)) -> UsersResponse:
    users = [user_service.serialize_user(record) for record in user_service.list_users()]
    return UsersResponse(users=users)


@router.post("/", response_model=UserPublic, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: UserCreate,
    _: UserPublic = Depends(deps.get_current_admin),
) -> UserPublic:
    if user_service.get_user_by_username(payload.username):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already exists")

    record = user_service.create_user(payload)
    return user_service.serialize_user(record)


@router.put("/{user_id}", response_model=UserPublic)
async def update_user(
    user_id: str,
    payload: UserUpdate,
    _: UserPublic = Depends(deps.get_current_admin),
) -> UserPublic:
    record = user_service.update_user(user_id, payload)
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user_service.serialize_user(record)


@router.delete("/{user_id}", response_model=None, status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: str,
    _: UserPublic = Depends(deps.get_current_admin),
) -> None:
    deleted = user_service.delete_user(user_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
