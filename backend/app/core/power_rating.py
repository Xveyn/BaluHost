"""
Power Rating Decorator for API Routes.

Provides the @requires_power decorator to automatically register
power demands when API endpoints are called.

Usage:
    from app.core.power_rating import requires_power
    from app.schemas.power import ServicePowerProperty

    @router.post("/backups")
    @requires_power(ServicePowerProperty.SURGE, timeout_seconds=3600)
    async def create_backup(...):
        ...
"""

from __future__ import annotations

import functools
import logging
import uuid
from typing import Callable, Optional, TypeVar, ParamSpec

from app.schemas.power import PowerProfile, ServicePowerProperty

logger = logging.getLogger(__name__)

P = ParamSpec("P")
T = TypeVar("T")


def _property_to_profile(prop: ServicePowerProperty) -> PowerProfile:
    """Convert ServicePowerProperty to PowerProfile."""
    return PowerProfile(prop.value)


# Backwards compatibility alias
def _rating_to_profile(rating: ServicePowerProperty) -> PowerProfile:
    """Convert ServicePowerProperty to PowerProfile (legacy name)."""
    return _property_to_profile(rating)


def requires_power(
    power_property: ServicePowerProperty,
    timeout_seconds: Optional[int] = None,
    description: Optional[str] = None
) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """
    Decorator to register power demand when an endpoint is called.

    The demand is registered before the endpoint executes and unregistered
    after it completes (or on timeout).

    Args:
        power_property: The service power property (IDLE, LOW, MEDIUM, SURGE)
        timeout_seconds: Auto-expire the demand after this duration.
                        Defaults to 300 (5 minutes) for safety.
        description: Human-readable description of why this power is needed

    Example:
        @router.post("/backups")
        @requires_power(ServicePowerProperty.SURGE, timeout_seconds=3600, description="Creating backup")
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
            profile = _property_to_profile(power_property)

            # Generate unique demand ID for this request
            func_name = func.__name__
            demand_id = f"{func_name}_{uuid.uuid4().hex[:8]}"

            demand_description = description or f"API call: {func_name}"

            try:
                # Register power demand
                await manager.register_demand(
                    source=demand_id,
                    level=profile,
                    power_property=power_property,
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


class PowerPropertyContext:
    """
    Context manager for power property in non-decorator scenarios.

    Usage:
        async with PowerPropertyContext(ServicePowerProperty.SURGE, "backup_operation"):
            # Long-running operation here
            pass
    """

    def __init__(
        self,
        power_property: ServicePowerProperty,
        source: str,
        timeout_seconds: Optional[int] = None,
        description: Optional[str] = None
    ):
        self.power_property = power_property
        self.source = source
        self.timeout_seconds = timeout_seconds
        self.description = description
        self._demand_id: Optional[str] = None

    async def __aenter__(self) -> "PowerPropertyContext":
        from app.services.power_manager import get_power_manager

        manager = get_power_manager()
        profile = _property_to_profile(self.power_property)

        self._demand_id = await manager.register_demand(
            source=self.source,
            level=profile,
            power_property=self.power_property,
            timeout_seconds=self.timeout_seconds,
            description=self.description
        )

        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        from app.services.power_manager import get_power_manager

        if self._demand_id:
            manager = get_power_manager()
            await manager.unregister_demand(self._demand_id)


# Backwards compatibility alias
PowerRatingContext = PowerPropertyContext


# Convenience function for programmatic demand registration
async def register_power_demand(
    source: str,
    power_property: ServicePowerProperty,
    timeout_seconds: Optional[int] = None,
    description: Optional[str] = None
) -> str:
    """
    Programmatically register a power demand.

    Returns the demand ID for later unregistration.

    Args:
        source: Unique identifier for this demand
        power_property: Required service power property (IDLE, LOW, MEDIUM, SURGE)
        timeout_seconds: Auto-expire after this duration
        description: Human-readable description

    Returns:
        The demand ID (same as source)
    """
    from app.services.power_manager import get_power_manager

    manager = get_power_manager()
    profile = _property_to_profile(power_property)

    return await manager.register_demand(
        source=source,
        level=profile,
        power_property=power_property,
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
