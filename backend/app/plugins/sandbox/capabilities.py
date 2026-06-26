"""Host-side capability layer for the plugin sandbox (Phase 3).

Every ``cap_call`` from an untrusted worker is dispatched here. The router is
the *enforcement* point: default-deny against the plugin's granted scopes, then
a narrow, validated host handler that runs with host privileges and returns
only a curated result. The acting ``user_id`` is taken from the host-resolved
``CapabilityContext`` (never from plugin args) so a plugin can never address a
foreign user's data.

The router takes its host dependencies (DB session factory, metrics reader,
notifier, audit logger) by injection; Phase 4 wires the production ones.
"""
import asyncio
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional

from app.services import plugin_storage_service
from app.services.plugin_storage_service import StorageQuotaError


@dataclass(frozen=True)
class CapabilityContext:
    """Host-resolved identity of the request a cap_call is serving."""

    user_id: int
    username: str
    role: str


class CapabilityError(Exception):
    """Internal: a plugin-caused failure mapped to a cap_result error code."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


# capability (operation) -> required grantable scope string
CAPABILITY_SCOPE: dict[str, str] = {
    "storage.get": "storage",
    "storage.set": "storage",
    "storage.delete": "storage",
    "storage.list": "storage",
    "core.system_metrics": "core.system_metrics",
    "core.notify": "core.notify",
}


class CapabilityRouter:
    """Default-deny dispatcher for a single sandboxed plugin."""

    def __init__(
        self,
        *,
        plugin_name: str,
        granted_scopes: frozenset[str],
        session_factory: Callable[[], Any],
        metrics_reader: Optional[Callable[[], dict]] = None,
        notifier: Optional[Callable[[CapabilityContext, dict], Awaitable[None]]] = None,
        audit_logger: Any = None,
    ):
        self._plugin_name = plugin_name
        self._granted_scopes = granted_scopes
        self._session_factory = session_factory
        self._metrics_reader = metrics_reader
        self._notifier = notifier
        self._audit_logger = audit_logger

    async def dispatch(self, capability: str, args: dict, context: CapabilityContext) -> dict:
        scope = CAPABILITY_SCOPE.get(capability)
        if scope is None:
            return {"error": "unknown_capability"}
        if scope not in self._granted_scopes:
            self._audit_denied(capability, context)
            return {"error": "denied"}
        try:
            if capability.startswith("storage."):
                return {"result": await self._storage(capability, args, context)}
            if capability == "core.system_metrics":
                return {"result": await self._system_metrics()}
            if capability == "core.notify":
                return {"result": await self._notify(args, context)}
        except CapabilityError as exc:
            return {"error": exc.code}
        return {"error": "unknown_capability"}

    # --- storage.* -------------------------------------------------------

    async def _storage(self, capability: str, args: dict, context: CapabilityContext) -> Any:
        op = capability.split(".", 1)[1]
        key = args.get("key")
        if op in ("get", "set", "delete") and not isinstance(key, str):
            raise CapabilityError("invalid_args")

        def run() -> Any:
            db = self._session_factory()
            try:
                if op == "get":
                    found, value = plugin_storage_service.get_value(
                        db, self._plugin_name, context.user_id, key
                    )
                    return value if found else None
                if op == "set":
                    plugin_storage_service.set_value(
                        db, self._plugin_name, context.user_id, key, args.get("value")
                    )
                    return None
                if op == "delete":
                    return plugin_storage_service.delete_value(
                        db, self._plugin_name, context.user_id, key
                    )
                if op == "list":
                    return plugin_storage_service.list_keys(
                        db, self._plugin_name, context.user_id
                    )
                raise CapabilityError("unknown_capability")
            finally:
                close = getattr(db, "close", None)
                if callable(close):
                    close()

        try:
            return await asyncio.to_thread(run)
        except StorageQuotaError:
            raise CapabilityError("storage_quota")

    # --- core.* (filled in Task 2) --------------------------------------

    async def _system_metrics(self) -> dict:
        if self._metrics_reader is None:
            raise CapabilityError("unavailable")
        return await asyncio.to_thread(self._metrics_reader)

    async def _notify(self, args: dict, context: CapabilityContext) -> None:
        if self._notifier is None:
            raise CapabilityError("unavailable")
        title = args.get("title")
        message = args.get("message")
        ntype = args.get("type", "info")
        if (
            not isinstance(title, str)
            or not isinstance(message, str)
            or not (1 <= len(title) <= 200)
            or not (1 <= len(message) <= 2000)
            or ntype not in ("info", "warning")
        ):
            raise CapabilityError("invalid_args")
        await self._notifier(context, {"title": title, "message": message, "type": ntype})

    # --- audit ----------------------------------------------------------

    def _audit_denied(self, capability: str, context: CapabilityContext) -> None:
        logger = self._audit_logger
        if logger is None:
            return
        try:
            logger.log_security_event(
                action="plugin_capability_denied",
                user=context.username,
                resource=f"plugin:{self._plugin_name}",
                details={"capability": capability, "scope": CAPABILITY_SCOPE.get(capability)},
                success=False,
            )
        except Exception:
            pass  # auditing must never break dispatch
