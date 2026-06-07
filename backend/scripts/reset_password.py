"""Offline password reset (backend-side rescue tool).

Run on the server where the backend is installed, e.g. when login is broken:
    python scripts/reset_password.py <username>
Prompts for the new password. Requires direct database access.
"""
from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

# Make the backend `app` package importable when run as a loose script.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.database import SessionLocal  # noqa: E402
from app.models.user import User  # noqa: E402
from passlib.context import CryptContext  # noqa: E402

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def reset_user_password(username: str, new_password: str) -> None:
    """Set *username*'s password hash directly in the DB. Raises ValueError if not found."""
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == username).first()
        if not user:
            raise ValueError(f"User '{username}' not found")
        user.hashed_password = pwd_context.hash(new_password)
        db.commit()
    finally:
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="BaluHost offline password reset")
    parser.add_argument("username", help="Username to reset")
    args = parser.parse_args()

    new_password = getpass.getpass("New password: ")
    confirm = getpass.getpass("Confirm password: ")
    if new_password != confirm:
        print("Error: passwords do not match", file=sys.stderr)
        return 1
    if not new_password:
        print("Error: password cannot be empty", file=sys.stderr)
        return 1
    try:
        reset_user_password(args.username, new_password)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(f"✓ Password reset for user: {args.username}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
