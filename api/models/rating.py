"""
Rating and review model for prompt feedback.
"""

from sqlalchemy import Column, String, Integer, Text, DateTime, ForeignKey, CheckConstraint, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid
from datetime import datetime

from api.database import Base


class PromptRating(Base):
    """Track ratings and reviews for prompts"""
    __tablename__ = "prompt_ratings"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    prompt_id = Column(UUID(as_uuid=True), ForeignKey("prompts.id"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    transaction_id = Column(UUID(as_uuid=True), ForeignKey("transactions.id"), nullable=True)
    rating = Column(Integer, nullable=False)
    review_title = Column(String(200), nullable=True)
    review_text = Column(Text, nullable=True)
    is_verified_purchase = Column(Boolean, default=False)
    helpful_count = Column(Integer, default=0)
    not_helpful_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    prompt = relationship("Prompt", back_populates="ratings")
    user = relationship("User", back_populates="ratings_given")
    transaction = relationship("Transaction", back_populates="rating")
    
    # Constraints
    __table_args__ = (
        CheckConstraint('rating >= 1 AND rating <= 5', name='check_rating_range'),
        Index('idx_prompt_user_rating', 'prompt_id', 'user_id', unique=True),  # One rating per user per prompt
    )
    
    def to_dict(self):
        return {
            "id": str(self.id),
            "prompt_id": str(self.prompt_id),
            "user_id": str(self.user_id),
            "rating": self.rating,
            "review_title": self.review_title,
            "review_text": self.review_text,
            "is_verified_purchase": self.is_verified_purchase,
            "helpful_count": self.helpful_count,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat()
        }


class RatingHelpfulness(Base):
    """Track whether users found reviews helpful"""
    __tablename__ = "rating_helpfulness"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    rating_id = Column(UUID(as_uuid=True), ForeignKey("prompt_ratings.id"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    is_helpful = Column(Boolean, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    rating = relationship("PromptRating")
    user = relationship("User")
    
    # Constraints
    __table_args__ = (
        Index('idx_rating_user_helpful', 'rating_id', 'user_id', unique=True),  # One vote per user per rating
    )


# Import required
from sqlalchemy import Boolean