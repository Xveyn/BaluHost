"""Emergency commands for local access only."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.core.database import SessionLocal
from app.models.user import User
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def reset_user_password(username: str, new_password: str) -> None:
    """Reset user password (emergency function).
    
    Args:
        username: Username to reset
        new_password: New password to set
        
    Raises:
        ValueError: If user not found
    """
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == username).first()
        
        if not user:
            raise ValueError(f"User '{username}' not found")
        
        # Hash new password
        hashed = pwd_context.hash(new_password)
        user.hashed_password = hashed
        
        db.commit()
        
    finally:
        db.close()
