"""Add scripts/ to sys.path so sibling test modules can import the script."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
