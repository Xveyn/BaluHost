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

    # Seed demo users (besides admin) - Always re-seed users since they're in-memory
    demo_users = [
        UserCreate(username="alex", email="alex@example.com", password="Demo1234", role="user"),
        UserCreate(username="maria", email="maria@example.com", password="Demo1234", role="user"),
    ]

    for user in demo_users:
        if not user_service.get_user_by_username(user.username):
            user_service.create_user(user)
            logger.info("Seeded demo user '%s'", user.username)

    # Check if files need to be seeded (only once)
    if _DEMO_MARKER.exists():
        logger.debug("Dev seed files already applied; skipping file creation")
        return

    # Seed demo folders/files once
    storage_root = Path(settings.nas_storage_path)
    docs_dir = storage_root / "Demo" / "Documents"
    media_dir = storage_root / "Demo" / "Media"
    for directory in (docs_dir, media_dir):
        directory.mkdir(parents=True, exist_ok=True)

    seed_files: Iterable[tuple[Path, str]] = (
        (
            docs_dir / "welcome.txt",
            "Welcome to Baluhost Dev Mode!\n\nThese files are for testing the interface only.\n",
        ),
        (
            media_dir / "readme.md",
            "# Demo Media\n\nPhotos or videos could be placed here.\n",
        ),
        (
            storage_root / "Notes.txt",
            "Notizen zum NAS Dev Mode. Setup: 2x5GB RAID1 (effektiv 5GB Speicher).\n",
        ),
    )

    for path, content in seed_files:
        if not path.exists():
            path.write_text(content, encoding="utf-8")

    # Mark seed as applied
    _DEMO_MARKER.write_text("Seed applied", encoding="utf-8")
    logger.info("Dev seed created demo users and sample files")
