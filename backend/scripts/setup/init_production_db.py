#!/usr/bin/env python3
"""Initialize production database with all tables and seed data."""

import sys
import os
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from passlib.context import CryptContext
from app.models import Base
from app.models.user import User
from app.core.config import get_settings

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def init_database():
    """Initialize database with tables and seed data."""
    settings = get_settings()

    # Get database URL from settings or environment
    db_url = settings.database_url or os.getenv("DATABASE_URL")
    if not db_url:
        raise ValueError("DATABASE_URL not found in settings or environment")

    print(f"Connecting to database: {db_url.split('@')[1] if '@' in db_url else db_url}")

    # Create engine
    engine = create_engine(db_url, echo=False)

    # Drop all tables (fresh start)
    print("Dropping all existing tables...")
    Base.metadata.drop_all(bind=engine)

    # Create all tables
    print("Creating all tables from models...")
    Base.metadata.create_all(bind=engine)

    # Create session
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    try:
        # Check if admin user exists
        existing_admin = db.query(User).filter(User.username == settings.admin_username).first()

        if not existing_admin:
            print(f"Creating admin user: {settings.admin_username}")
            admin = User(
                username=settings.admin_username,
                email=settings.admin_email,
                hashed_password=pwd_context.hash(settings.admin_password),
                role="admin",
                is_active=True,
            )
            db.add(admin)
            db.commit()
            print(f"✅ Admin user created: {settings.admin_username}")
        else:
            print(f"Admin user already exists: {settings.admin_username}")

        # Mark alembic as up-to-date (stamp head)
        print("Marking database as up-to-date with migrations...")
        from alembic.config import Config
        from alembic import command

        alembic_cfg = Config("alembic.ini")
        command.stamp(alembic_cfg, "head")

        print("\n✅ Database initialization completed successfully!")
        print(f"\nAdmin credentials:")
        print(f"  Username: {settings.admin_username}")
        print(f"  Password: {settings.admin_password}")
        print(f"\n⚠️  IMPORTANT: Change the admin password after first login!")

    except Exception as e:
        print(f"❌ Error during initialization: {e}")
        db.rollback()
        raise
    finally:
        db.close()

if __name__ == "__main__":
    init_database()
