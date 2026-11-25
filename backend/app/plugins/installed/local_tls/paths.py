"""Datenverzeichnis und Lauf-Lock des Plugins local_tls."""
import fcntl
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

DATA_DIR = Path("/var/lib/baluhost/plugins/local_tls")


class AlreadyRunning(Exception):
    """Ein anderer lego-Lauf haelt den Lock bereits."""


def ensure_dirs(data_dir: Path) -> None:
    """Legt das Datenverzeichnis (und lego/, lego-staging/) mit Modus 0700 an."""
    for d in (data_dir, data_dir / "lego", data_dir / "lego-staging"):
        d.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(d, 0o700)


@contextmanager
def lock(data_dir: Path) -> Iterator[None]:
    """Nicht blockierender flock auf ``<data>/.lock``; sonst AlreadyRunning."""
    fd = os.open(data_dir / ".lock", os.O_RDWR | os.O_CREAT, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise AlreadyRunning("another run is in progress") from None
        yield
    finally:
        os.close(fd)  # gibt den flock frei
