"""
Power Rating Decorator for API Routes.

Provides the @requires_power decorator to automatically register
power demands when API endpoints are called.

Usage:
    from app.core.power_rating import requires_power
    from app.schemas.power import PowerRating

    @router.post("/backups")
    @requires_power(PowerRating.SURGE, timeout_seconds=3600)
    async def create_backup(...):
        ...
"""

from __future__ import annotations

import functools
import logging
import uuid
from typing import Callable, Optional, TypeVar, ParamSpec

from app.schemas.power import PowerProfile, PowerRating

logger = logging.getLogger(__name__)

P = ParamSpec("P")
T = TypeVar("T")


def _rating_to_profile(rating: PowerRating) -> PowerProfile:
    """Convert PowerRating to PowerProfile."""
    return PowerProfile(rating.value)


def requires_power(
    rating: PowerRating,
    timeout_seconds: Optional[int] = None,
    description: Optional[str] = None
) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """
    Decorator to register power demand when an endpoint is called.

    The demand is registered before the endpoint executes and unregistered
    after it completes (or on timeout).

    Args:
        rating: The power level required for this endpoint
        timeout_seconds: Auto-expire the demand after this duration.
                        Defaults to 300 (5 minutes) for safety.
        description: Human-readable description of why this power is needed

    Example:
        @router.post("/backups")
        @requires_power(PowerRating.SURGE, timeout_seconds=3600, description="Creating backup")
        async def create_backup(request: BackupRequest):
            ...
    """
    # Default timeout for safety
    if timeout_seconds is None:
        timeout_seconds = 300  # 5 minutes default

    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @functools.wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            # Import here to avoid circular imports
            from app.services.power_manager import get_power_manager

            manager = get_power_manager()
            profile = _rating_to_profile(rating)

            # Generate unique demand ID for this request
            func_name = func.__name__
            demand_id = f"{func_name}_{uuid.uuid4().hex[:8]}"

            demand_description = description or f"API call: {func_name}"

            try:
                # Register power demand
                await manager.register_demand(
                    source=demand_id,
                    level=profile,
                    timeout_seconds=timeout_seconds,
                    description=demand_description
                )

                # Execute the actual endpoint
                return await func(*args, **kwargs)

            finally:
                # Always unregister demand when done
                await manager.unregister_demand(demand_id)

        return wrapper

    return decorator


class PowerRatingContext:
    """
    Context manager for power rating in non-decorator scenarios.

    Usage:
        async with PowerRatingContext(PowerRating.SURGE, "backup_operation"):
            # Long-running operation here
            pass
    """

    def __init__(
        self,
        rating: PowerRating,
        source: str,
        timeout_seconds: Optional[int] = None,
        description: Optional[str] = None
    ):
        self.rating = rating
        self.source = source
        self.timeout_seconds = timeout_seconds
        self.description = description
        self._demand_id: Optional[str] = None

    async def __aenter__(self) -> "PowerRatingContext":
        from app.services.power_manager import get_power_manager

        manager = get_power_manager()
        profile = _rating_to_profile(self.rating)

        self._demand_id = await manager.register_demand(
            source=self.source,
            level=profile,
            timeout_seconds=self.timeout_seconds,
            description=self.description
        )

        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        from app.services.power_manager import get_power_manager

        if self._demand_id:
            manager = get_power_manager()
            await manager.unregister_demand(self._demand_id)


# Convenience function for programmatic demand registration
async def register_power_demand(
    source: str,
    rating: PowerRating,
    timeout_seconds: Optional[int] = None,
    description: Optional[str] = None
) -> str:
    """
    Programmatically register a power demand.

    Returns the demand ID for later unregistration.

    Args:
        source: Unique identifier for this demand
        rating: Required power level
        timeout_seconds: Auto-expire after this duration
        description: Human-readable description

    Returns:
        The demand ID (same as source)
    """
    from app.services.power_manager import get_power_manager

    manager = get_power_manager()
    profile = _rating_to_profile(rating)

    return await manager.register_demand(
        source=source,
        level=profile,
        timeout_seconds=timeout_seconds,
        description=description
    )


async def unregister_power_demand(source: str) -> bool:
    """
    Unregister a previously registered power demand.

    Args:
        source: The demand source/ID to unregister

    Returns:
        True if demand was found and removed
    """
    from app.services.power_manager import get_power_manager

    manager = get_power_manager()
    return await manager.unregister_demand(source)
