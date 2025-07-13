"""
Social sharing model for tracking prompt shares.
"""

from sqlalchemy import Column, String, DateTime, ForeignKey, JSON, Integer, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid
from datetime import datetime

from api.database import Base


class PromptShare(Base):
    """Track prompt sharing activity"""
    __tablename__ = "prompt_shares"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    prompt_id = Column(UUID(as_uuid=True), ForeignKey("prompts.id"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)  # Can be anonymous
    share_code = Column(String(50), unique=True, nullable=False, index=True)
    platform = Column(String(50), nullable=False)  # email, twitter, linkedin, facebook, link
    recipient_email = Column(String(255), nullable=True)  # For email shares
    click_count = Column(Integer, default=0)
    conversion_count = Column(Integer, default=0)  # Shares that led to purchases
    share_metadata = Column(JSON, default={})
    is_active = Column(Boolean, default=True)
    expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    prompt = relationship("Prompt", back_populates="shares")
    user = relationship("User", back_populates="shared_prompts")
    
    @staticmethod
    def generate_share_code() -> str:
        """Generate a unique share code"""
        import secrets
        return f"share_{secrets.token_urlsafe(16)}"
    
    def record_click(self):
        """Record a click on the share link"""
        self.click_count += 1
    
    def record_conversion(self):
        """Record a conversion from this share"""
        self.conversion_count += 1
    
    def to_dict(self):
        return {
            "id": str(self.id),
            "prompt_id": str(self.prompt_id),
            "user_id": str(self.user_id) if self.user_id else None,
            "share_code": self.share_code,
            "platform": self.platform,
            "click_count": self.click_count,
            "conversion_count": self.conversion_count,
            "created_at": self.created_at.isoformat()
        }