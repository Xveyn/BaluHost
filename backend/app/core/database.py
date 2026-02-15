"""Database configuration and session management."""
from typing import Generator
from pathlib import Path
import os
import logging

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import NullPool, QueuePool

from app.core.config import settings
from app.models import Base

logger = logging.getLogger(__name__)


# SQLite-specific optimizations
def _configure_sqlite(dbapi_conn, _connection_record):
    """Configure SQLite for optimal performance."""
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


# PostgreSQL connection pool settings (can be overridden via env vars)
def _get_pg_pool_config() -> dict:
    """Get PostgreSQL connection pool configuration from environment."""
    return {
        "pool_size": int(os.getenv("DB_POOL_SIZE", "10")),
        "max_overflow": int(os.getenv("DB_MAX_OVERFLOW", "20")),
        "pool_timeout": int(os.getenv("DB_POOL_TIMEOUT", "30")),
        "pool_recycle": int(os.getenv("DB_POOL_RECYCLE", "3600")),  # 1 hour
        "pool_pre_ping": True,  # Verify connections before using
        "echo": os.getenv("DB_ECHO", "false").lower() == "true",
        "echo_pool": os.getenv("DB_ECHO_POOL", "false").lower() == "true"
    }


# Database URL
if settings.is_dev_mode:
    # Dev mode: SQLite in dev-storage (default)
    db_path = Path(settings.nas_storage_path).parent / "baluhost.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    DATABASE_URL = settings.database_url or f"sqlite:///{db_path}"
else:
    # Production mode: PostgreSQL (recommended) or SQLite fallback
    if settings.database_url:
        DATABASE_URL = settings.database_url
    else:
        # Fallback to SQLite in production (not recommended)
        DATABASE_URL = "sqlite:///var/lib/baluhost/baluhost.db"
        logger.warning(
            "No DATABASE_URL configured. Using SQLite fallback. "
            "PostgreSQL is strongly recommended for production!"
        )

# Log database configuration (redact password)
safe_url = DATABASE_URL
if "@" in DATABASE_URL:
    # Redact password from logs
    parts = DATABASE_URL.split("@")
    user_pass = parts[0].split("//")[1]
    if ":" in user_pass:
        user = user_pass.split(":")[0]
        safe_url = DATABASE_URL.replace(user_pass, f"{user}:***")
logger.info(f"Database URL: {safe_url}")

# Create engine with appropriate configuration
if DATABASE_URL.startswith("sqlite"):
    logger.info("Using SQLite database with WAL mode")
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
        pool_pre_ping=True,
        echo=os.getenv("DB_ECHO", "false").lower() == "true"
    )
    # Apply SQLite optimizations
    event.listen(engine, "connect", _configure_sqlite)

elif DATABASE_URL.startswith("postgresql"):
    logger.info("Using PostgreSQL database with connection pooling")
    pool_config = _get_pg_pool_config()
    logger.info(
        f"PostgreSQL Pool: size={pool_config['pool_size']}, "
        f"max_overflow={pool_config['max_overflow']}, "
        f"timeout={pool_config['pool_timeout']}s, "
        f"recycle={pool_config['pool_recycle']}s"
    )

    engine = create_engine(
        DATABASE_URL,
        poolclass=QueuePool,
        **pool_config
    )

else:
    # Unknown database type, use basic configuration
    logger.warning(f"Unknown database type in URL: {DATABASE_URL}")
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
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
    """Initialize database tables.

    For PostgreSQL (production), schema is managed by Alembic migrations.
    For SQLite (dev mode), create_all ensures tables exist without migrations.
    """
    if DATABASE_URL.startswith("postgresql"):
        logger.debug("PostgreSQL detected — schema managed by Alembic, skipping create_all()")
        return
    Base.metadata.create_all(bind=engine)
