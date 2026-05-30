"""Detect boost-eligible processes for the CPU power authority.

`match_boost_rules` is pure (testable without psutil). A psutil adapter
(`snapshot_processes`) feeds it live data from the enforcement loop (Task 8).
"""
from __future__ import annotations

import fnmatch
import logging
from dataclasses import dataclass
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

# Wrapper processes that exist ONLY during an active Steam/Proton/Wine game
# session (not when Steam merely idles in the tray).
GAME_WRAPPERS = (
    "pressure-vessel", "pv-bwrap", "proton",
    "wine", "wine64", "wineserver", "wine64-preloader",
)


@dataclass
class ProcInfo:
    name: str
    cmdline: str = ""


def _is_game_session(procs: List[ProcInfo]) -> bool:
    for p in procs:
        name = (p.name or "").lower()
        if name in GAME_WRAPPERS or name.startswith("wine"):
            return True
        if name == "reaper" and "steamlaunch" in (p.cmdline or "").lower():
            return True
    return False


def _glob_match(procs: List[ProcInfo], pattern: str) -> bool:
    pat = (pattern or "").lower()
    for p in procs:
        name = (p.name or "").lower()
        if fnmatch.fnmatch(name, pat) or (len(name) == 15 and pat.startswith(name)):
            return True
    return False


def match_boost_rules(procs: List[ProcInfo], rules: List[dict]) -> Tuple[bool, Optional[int]]:
    """Return (any_hit, effective_target_mhz).

    effective_target_mhz = highest target among matched rules; ``None`` means
    full boost and beats any finite cap.
    """
    matched_targets: List[Optional[int]] = []
    for rule in rules:
        if not rule.get("enabled", True):
            continue
        kind = rule.get("kind")
        hit = False
        if kind == "game_session":
            hit = _is_game_session(procs)
        elif kind == "process_glob" and rule.get("pattern"):
            hit = _glob_match(procs, rule["pattern"])
        if hit:
            matched_targets.append(rule.get("target_max_mhz"))

    if not matched_targets:
        return False, None
    if any(t is None for t in matched_targets):
        return True, None
    return True, max(matched_targets)
