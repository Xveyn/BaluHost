"""Database model for rate limit configuration."""

from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.sql import func
from app.models.base import Base


class RateLimitConfig(Base):
    """Configuration for API rate limits."""
    
    __tablename__ = "rate_limit_configs"
    
    id = Column(Integer, primary_key=True, index=True)
    endpoint_type = Column(String(50), unique=True, nullable=False, index=True)
    limit_string = Column(String(20), nullable=False)  # e.g., "5/minute", "100/hour"
    description = Column(String(200), nullable=True)
    enabled = Column(Boolean, default=True, nullable=False)
    
    # Audit fields
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    updated_by = Column(Integer, nullable=True)  # User ID who last updated
    
    def __repr__(self):
        return f"<RateLimitConfig(endpoint_type='{self.endpoint_type}', limit='{self.limit_string}')>"
