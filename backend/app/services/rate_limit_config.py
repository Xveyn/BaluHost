"""Service for managing rate limit configurations."""

from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models.rate_limit_config import RateLimitConfig
from app.schemas.rate_limit_config import RateLimitConfigCreate, RateLimitConfigUpdate


class RateLimitConfigService:
    """Service for managing rate limit configurations."""
    
    @staticmethod
    def get_all(db: Session) -> list[RateLimitConfig]:
        """Get all rate limit configurations."""
        return db.execute(select(RateLimitConfig)).scalars().all()
    
    @staticmethod
    def get_by_endpoint_type(db: Session, endpoint_type: str) -> Optional[RateLimitConfig]:
        """Get rate limit configuration by endpoint type."""
        return db.execute(
            select(RateLimitConfig).where(RateLimitConfig.endpoint_type == endpoint_type)
        ).scalar_one_or_none()
    
    @staticmethod
    def get_enabled_configs(db: Session) -> dict[str, str]:
        """Get all enabled rate limit configurations as a dictionary."""
        configs = db.execute(
            select(RateLimitConfig).where(RateLimitConfig.enabled == True)
        ).scalars().all()
        
        return {config.endpoint_type: config.limit_string for config in configs}
    
    @staticmethod
    def create(db: Session, config: RateLimitConfigCreate, user_id: int) -> RateLimitConfig:
        """Create a new rate limit configuration."""
        db_config = RateLimitConfig(
            endpoint_type=config.endpoint_type,
            limit_string=config.limit_string,
            description=config.description,
            enabled=config.enabled,
            updated_by=user_id
        )
        db.add(db_config)
        db.commit()
        db.refresh(db_config)
        return db_config
    
    @staticmethod
    def update(
        db: Session,
        endpoint_type: str,
        config_update: RateLimitConfigUpdate,
        user_id: int
    ) -> Optional[RateLimitConfig]:
        """Update an existing rate limit configuration."""
        db_config = RateLimitConfigService.get_by_endpoint_type(db, endpoint_type)
        
        if not db_config:
            return None
        
        # Update only provided fields
        if config_update.limit_string is not None:
            db_config.limit_string = config_update.limit_string
        if config_update.description is not None:
            db_config.description = config_update.description
        if config_update.enabled is not None:
            db_config.enabled = config_update.enabled
        
        db_config.updated_by = user_id
        
        db.commit()
        db.refresh(db_config)
        return db_config
    
    @staticmethod
    def delete(db: Session, endpoint_type: str) -> bool:
        """Delete a rate limit configuration."""
        db_config = RateLimitConfigService.get_by_endpoint_type(db, endpoint_type)
        
        if not db_config:
            return False
        
        db.delete(db_config)
        db.commit()
        return True
    
    @staticmethod
    def seed_defaults(db: Session) -> None:
        """Seed default rate limit configurations if none exist."""
        existing = db.execute(select(RateLimitConfig)).first()
        
        if existing:
            return  # Already seeded
        
        # Default rate limits
        defaults = [
            ("auth_login", "5/minute", "Login endpoint - prevent brute force"),
            ("auth_register", "3/minute", "Registration endpoint - prevent spam"),
            ("mobile_register", "3/minute", "Mobile device registration"),
            ("file_upload", "20/minute", "File upload endpoint"),
            ("file_download", "100/minute", "File download endpoint"),
            ("file_list", "60/minute", "File listing endpoint"),
            ("file_delete", "30/minute", "File deletion endpoint"),
            ("share_create", "10/minute", "Share creation endpoint"),
            ("share_list", "60/minute", "Share listing endpoint"),
            ("public_share", "100/minute", "Public share access"),
            ("admin_operations", "30/minute", "Admin operations"),
            ("user_operations", "30/minute", "User management operations"),
            ("system_monitor", "120/minute", "System monitoring endpoints"),
            ("vpn_operations", "10/minute", "VPN configuration operations"),
        ]
        
        for endpoint_type, limit_string, description in defaults:
            db_config = RateLimitConfig(
                endpoint_type=endpoint_type,
                limit_string=limit_string,
                description=description,
                enabled=True
            )
            db.add(db_config)
        
        db.commit()
