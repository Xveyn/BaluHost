"""Database configuration and session management."""
from typing import Generator
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker, Session

from app.core.config import settings
from app.models import Base


# SQLite-specific optimizations for Raspberry Pi
def _configure_sqlite(dbapi_conn, _connection_record):
    """Configure SQLite for optimal performance on Raspberry Pi."""
    cursor = dbapi_conn.cursor()
    # Enable Write-Ahead Logging for better concurrent access
    cursor.execute("PRAGMA journal_mode=WAL")
    # Synchronous mode for balance between speed and safety
    cursor.execute("PRAGMA synchronous=NORMAL")
    # Cache size (2000 pages = ~8MB)
    cursor.execute("PRAGMA cache_size=-8000")
    # Enable foreign keys
    cursor.execute("PRAGMA foreign_keys=ON")
    # Memory-mapped I/O (32MB)
    cursor.execute("PRAGMA mmap_size=33554432")
    cursor.close()


# Database URL
if settings.is_dev_mode:
    # Dev mode: SQLite in dev-storage
    db_path = Path(settings.nas_storage_path).parent / "baluhost.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    DATABASE_URL = f"sqlite:///{db_path}"
else:
    # Production mode: SQLite in /var/lib/baluhost or custom path
    DATABASE_URL = settings.database_url or "sqlite:///var/lib/baluhost/baluhost.db"

# Create engine
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
        pool_pre_ping=True,
        echo=False  # Set to True for SQL debugging
    )
    # Apply SQLite optimizations
    event.listen(engine, "connect", _configure_sqlite)
else:
    # PostgreSQL support (future)
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
        echo=False
    )

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    """
    Dependency to get database session.
    
    Usage in FastAPI:
        @router.get("/users")
        def get_users(db: Session = Depends(get_db)):
            return db.query(User).all()
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """
    Initialize database tables.
    Should be called on application startup.
    """
    Base.metadata.create_all(bind=engine)
