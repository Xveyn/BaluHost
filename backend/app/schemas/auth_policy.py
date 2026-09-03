from pydantic import BaseModel, Field

MIN_WINDOW_SECONDS = 60
MAX_WINDOW_SECONDS = 604800  # 7 days

# Session limits. 0 minutes is the documented "off" value for the idle logout;
# every other bound exists to keep an admin from configuring something that
# cannot work (a 30 s warning nobody can react to, a 3-day access token).
MAX_IDLE_MINUTES = 1440  # 24 h
MIN_WARNING_SECONDS = 10
MAX_WARNING_SECONDS = 300
MIN_TOKEN_MINUTES = 5
MAX_TOKEN_MINUTES = 1440  # 24 h


class AuthPolicyResponse(BaseModel):
    pin_login_enabled: bool
    pin_grace_window_seconds: int
    idle_timeout_minutes: int
    idle_warning_seconds: int
    access_token_minutes: int


class AuthPolicyUpdate(BaseModel):
    pin_login_enabled: bool | None = None
    pin_grace_window_seconds: int | None = Field(
        default=None, ge=MIN_WINDOW_SECONDS, le=MAX_WINDOW_SECONDS
    )
    idle_timeout_minutes: int | None = Field(
        default=None, ge=0, le=MAX_IDLE_MINUTES,
        description="Minutes of inactivity before the logout warning; 0 disables it",
    )
    idle_warning_seconds: int | None = Field(
        default=None, ge=MIN_WARNING_SECONDS, le=MAX_WARNING_SECONDS,
        description="Countdown shown before the automatic logout",
    )
    access_token_minutes: int | None = Field(
        default=None, ge=MIN_TOKEN_MINUTES, le=MAX_TOKEN_MINUTES,
        description="Lifetime of a newly issued access token",
    )


class SessionPolicyResponse(BaseModel):
    """The two numbers the idle hook needs - readable by any logged-in user.

    Deliberately does NOT carry the token TTL: the client never acts on it, and
    the PIN policy is admin business.
    """

    idle_timeout_minutes: int
    idle_warning_seconds: int
