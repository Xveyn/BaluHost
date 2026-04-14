"""Make the BaluHost backend package importable for cross-repo schema tests.

The shape contract between the marketplace index builder and BaluHost is
enforced by validating the emitted ``index.json`` against the real Pydantic
schema in ``backend/app/plugins/marketplace.py``. When this directory is
eventually split into its own repo, this file is replaced with a
``pip install baluhost-marketplace-schema`` (or similar) so the test still
runs, but today the backend lives next door.
"""
from __future__ import annotations

import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent.parent / "backend"
if _BACKEND.exists() and str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
