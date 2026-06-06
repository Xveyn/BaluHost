from pydantic import BaseModel, Field

MIN_WINDOW_SECONDS = 60
MAX_WINDOW_SECONDS = 604800  # 7 days


class AuthPolicyResponse(BaseModel):
    pin_login_enabled: bool
    pin_grace_window_seconds: int


class AuthPolicyUpdate(BaseModel):
    pin_login_enabled: bool | None = None
    pin_grace_window_seconds: int | None = Field(
        default=None, ge=MIN_WINDOW_SECONDS, le=MAX_WINDOW_SECONDS
    )
