"""Server-defined catalog of capability scopes grantable to external plugins.

Single source of truth for the scope-picker UI. Human labels/descriptions live
in frontend i18n (`scopeDescriptions.<key>`), exactly like `permissionDescriptions`.
Backend-tier keys are DERIVED from `CAPABILITY_SCOPE` so they cannot drift from
what the CapabilityRouter actually enforces.
"""
from dataclasses import dataclass
from typing import Literal, Tuple

from app.plugins.sandbox.capabilities import CAPABILITY_SCOPE


@dataclass(frozen=True)
class ScopeInfo:
    key: str
    tier: Literal["frontend", "backend"]
    dangerous: bool


# Frontend-tier keys mirror client/src/lib/plugin-sandbox/scopeCatalog.ts.
_FRONTEND_SCOPES = ("read:system-info", "read:storage", "read:power")

SCOPE_CATALOG: Tuple[ScopeInfo, ...] = (
    *(ScopeInfo(k, "frontend", False) for k in _FRONTEND_SCOPES),
    *(ScopeInfo(v, "backend", False) for v in sorted(set(CAPABILITY_SCOPE.values()))),
)

CATALOG_KEYS = frozenset(s.key for s in SCOPE_CATALOG)
