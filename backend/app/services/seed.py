from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable

from app.core.config import settings
from app.schemas.user import UserCreate
from app.services import users as user_service

logger = logging.getLogger(__name__)

_DEMO_MARKER = Path(settings.nas_storage_path) / ".dev_seed_applied"


def seed_dev_data() -> None:
    if not settings.is_dev_mode:
        return

    if _DEMO_MARKER.exists():
        logger.debug("Dev seed already applied; skipping")
        return

    # Seed demo users (besides admin)
    demo_users = [
        UserCreate(username="alex", email="alex@example.com", password="demo123", role="user"),
        UserCreate(username="maria", email="maria@example.com", password="demo123", role="user"),
    ]

    for user in demo_users:
        if not user_service.get_user_by_username(user.username):
            user_service.create_user(user)
            logger.info("Seeded demo user '%s'", user.username)

    # Seed demo folders/files once
    storage_root = Path(settings.nas_storage_path)
    docs_dir = storage_root / "Demo" / "Documents"
    media_dir = storage_root / "Demo" / "Media"
    for directory in (docs_dir, media_dir):
        directory.mkdir(parents=True, exist_ok=True)

    seed_files: Iterable[tuple[Path, str]] = (
        (
            docs_dir / "welcome.txt",
            "Willkommen bei Baluhost Dev Mode!\n\nDiese Dateien dienen nur zum Testen der Oberfläche.\n",
        ),
        (
            media_dir / "readme.md",
            "# Demo Medien\n\nHier könnten Fotos oder Videos liegen.\n",
        ),
        (
            storage_root / "Notes.txt",
            "Notizen zum NAS Dev Mode. Quota: 10 GB.\n",
        ),
    )

    for path, content in seed_files:
        if not path.exists():
            path.write_text(content, encoding="utf-8")

    # Mark seed as applied
    _DEMO_MARKER.write_text("Seed applied", encoding="utf-8")
    logger.info("Dev seed created demo users and sample files")
