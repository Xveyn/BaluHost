from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional

from app.schemas.system import RaidDevice


@dataclass
class MdstatInfo:
    blocks: Optional[int] = None
    resync_progress: Optional[float] = None


def _parse_mdstat(content: str) -> Dict[str, MdstatInfo]:
    arrays: Dict[str, MdstatInfo] = {}
    current: Optional[str] = None

    for raw_line in content.splitlines():
        line = raw_line.rstrip()
        if not line:
            continue
        if line.startswith("Personalities") or line.startswith("unused devices"):
            continue

        if not line.startswith(" "):
            parts = line.split()
            if not parts:
                continue
            name = parts[0].rstrip(":")
            arrays[name] = MdstatInfo()
            current = name
            continue

        if current is None:
            continue

        info = arrays[current]
        if info.blocks is None:
            # Accept numbers with optional commas (e.g. "2,096,128 blocks")
            match = re.search(r"([\d,]+)\s+blocks", line)
            if match:
                try:
                    info.blocks = int(match.group(1).replace(",", ""))
                except ValueError:  # pragma: no cover - defensive fallback
                    info.blocks = None

        lowered = line.lower()
        if info.resync_progress is None and any(
            keyword in lowered for keyword in ("resync", "recover", "rebuild", "reshape", "check")
        ):
            progress_match = re.search(r"(\d+(?:\.\d+)?)%", line)
            if progress_match:
                try:
                    info.resync_progress = float(progress_match.group(1))
                except ValueError:  # pragma: no cover - defensive conversion
                    info.resync_progress = None
            # If no explicit percentage is present, try to infer progress from a fraction like (259212/2096128).
            if info.resync_progress is None:
                frac_match = re.search(r"\(([\d,]+)\/([\d,]+)\)", line)
                if frac_match:
                    try:
                        num = int(frac_match.group(1).replace(",", ""))
                        den = int(frac_match.group(2).replace(",", ""))
                        if den > 0:
                            info.resync_progress = (num / den) * 100.0
                    except ValueError:  # pragma: no cover - defensive
                        pass

    return arrays


def _extract_detail_value(detail: str, key: str) -> Optional[str]:
    pattern = re.compile(rf"^\s*{re.escape(key)}\s*:\s*(.+)$", re.MULTILINE)
    match = pattern.search(detail)
    if match:
        return match.group(1).strip()
    return None


def _map_device_state(state_text: str) -> str:
    text = state_text.lower()
    if "faulty" in text or "failed" in text:
        return "failed"
    if "remove" in text:
        return "removed"
    if "spare" in text and ("rebuild" in text or "recover" in text):
        return "rebuilding"
    if "rebuild" in text or "recover" in text:
        return "rebuilding"
    if "spare" in text:
        return "spare"
    if "blocked" in text:
        return "blocked"
    if "writemostly" in text:
        return "write-mostly"
    if "sync" in text or "active" in text:
        return "active"
    return text or "unknown"


def _derive_array_status(
    state_text: Optional[str],
    progress: Optional[float],
    devices: List[RaidDevice],
    sync_action: Optional[str] = None,
) -> str:
    if state_text:
        lowered = state_text.lower()
        if "check" in lowered:
            return "checking"
        if any(keyword in lowered for keyword in ("resync", "recover", "rebuild", "reshape")):
            return "rebuilding"
        if "degraded" in lowered or "faulty" in lowered:
            return "degraded"
        if "inactive" in lowered or "stop" in lowered:
            return "inactive"

    if progress is not None:
        if sync_action and sync_action.strip().lower() == "check":
            return "checking"
        return "rebuilding"

    if any(dev.state in {"failed", "removed"} for dev in devices):
        return "degraded"

    return "optimal"
