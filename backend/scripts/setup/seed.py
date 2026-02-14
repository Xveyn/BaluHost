"""
Seed script for database initialization.

This script populates the database with initial data:
- Admin user
- Demo users
- Demo file metadata
"""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal, init_db
from app.models.user import User
from app.models.file_metadata import FileMetadata
from app.schemas.user import UserCreate
from app.services import users as user_service


def seed_users(db: Session) -> None:
    """Seed initial users into database."""
    print("🌱 Seeding users...")
    
    # Ensure admin user exists
    admin = user_service.get_user_by_username(settings.admin_username, db=db)
    if not admin:
        print(f"  Creating admin user: {settings.admin_username}")
        user_service.create_user(
            UserCreate(
                username=settings.admin_username,
                email=settings.admin_email,
                password=settings.admin_password,
                role="admin"
            ),
            db=db
        )
    else:
        print(f"  Admin user already exists: {settings.admin_username}")
    
    # Create demo users in dev mode
    if settings.is_dev_mode:
        demo_users = [
            {"username": "alice", "email": "alice@example.com", "password": "alice123", "role": "user"},
            {"username": "bob", "email": "bob@example.com", "password": "bob123", "role": "user"},
        ]
        
        for demo_user in demo_users:
            existing = user_service.get_user_by_username(demo_user["username"], db=db)
            if not existing:
                print(f"  Creating demo user: {demo_user['username']}")
                user_service.create_user(
                    UserCreate(**demo_user),
                    db=db
                )
            else:
                print(f"  Demo user already exists: {demo_user['username']}")
    
    print("✅ User seeding complete")


def seed_file_metadata(db: Session) -> None:
    """Seed demo file metadata into database."""
    if not settings.is_dev_mode:
        print("⏭️  Skipping file metadata seeding (not in dev mode)")
        return
    
    print("🌱 Seeding file metadata...")
    
    # Get admin and demo users
    admin = user_service.get_user_by_username(settings.admin_username, db=db)
    alice = user_service.get_user_by_username("alice", db=db)
    bob = user_service.get_user_by_username("bob", db=db)
    
    if not admin:
        print("  ⚠️  Admin user not found, skipping file metadata")
        return
    
    # Demo file structure
    demo_files = [
        # Root directories
        {"path": "Documents", "name": "Documents", "owner_id": admin.id, "is_directory": True, "size_bytes": 0},
        {"path": "Photos", "name": "Photos", "owner_id": admin.id, "is_directory": True, "size_bytes": 0},
        {"path": "Videos", "name": "Videos", "owner_id": admin.id, "is_directory": True, "size_bytes": 0},
        {"path": "Music", "name": "Music", "owner_id": admin.id, "is_directory": True, "size_bytes": 0},
        
        # Documents
        {"path": "Documents/README.txt", "name": "README.txt", "owner_id": admin.id, "is_directory": False, "size_bytes": 1024, "mime_type": "text/plain", "parent_path": "Documents"},
        {"path": "Documents/Report.pdf", "name": "Report.pdf", "owner_id": admin.id, "is_directory": False, "size_bytes": 512000, "mime_type": "application/pdf", "parent_path": "Documents"},
        
        # Photos
        {"path": "Photos/vacation.jpg", "name": "vacation.jpg", "owner_id": admin.id if not alice else alice.id, "is_directory": False, "size_bytes": 2048000, "mime_type": "image/jpeg", "parent_path": "Photos"},
        {"path": "Photos/family.png", "name": "family.png", "owner_id": admin.id if not bob else bob.id, "is_directory": False, "size_bytes": 1024000, "mime_type": "image/png", "parent_path": "Photos"},
    ]
    
    created_count = 0
    for file_data in demo_files:
        # Check if already exists
        existing = db.query(FileMetadata).filter(FileMetadata.path == file_data["path"]).first()
        if existing:
            print(f"  File metadata already exists: {file_data['path']}")
            continue
        
        file_meta = FileMetadata(**file_data)
        db.add(file_meta)
        created_count += 1
        print(f"  Created: {file_data['path']}")
    
    db.commit()
    print(f"✅ File metadata seeding complete ({created_count} new entries)")


def main() -> None:
    """Main seed function."""
    print("🚀 Starting database seeding...")
    print(f"   Database: {settings.database_url or 'SQLite (default)'}")
    print(f"   Dev Mode: {settings.is_dev_mode}")
    print()
    
    # Initialize database tables
    print("📦 Initializing database schema...")
    init_db()
    print("✅ Schema initialized")
    print()
    
    # Get database session
    db = SessionLocal()
    try:
        seed_users(db)
        print()
        seed_file_metadata(db)
        print()
        print("🎉 Database seeding completed successfully!")
    except Exception as e:
        print(f"❌ Error during seeding: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
