"""Game library storage usage endpoints (read-only, auto-discovered)."""
from fastapi import APIRouter, Depends, Request, Response

from app.api import deps
from app.core.rate_limiter import user_limiter, get_limit
from app.schemas.games import GameLibrariesResponse
from app.schemas.user import UserPublic
from app.services.game_libraries import service as game_libraries_service

router = APIRouter()


@router.get("/libraries", response_model=GameLibrariesResponse)
@user_limiter.limit(get_limit("system_monitor"))
def get_game_libraries(
    request: Request,
    response: Response,
    _: UserPublic = Depends(deps.get_current_user),
) -> GameLibrariesResponse:
    """Detected game libraries with per-game size."""
    return game_libraries_service.get_game_libraries()
