from sqlalchemy import Column, String, Integer, Numeric, Text, DateTime, ForeignKey, Enum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
import enum
from api.database import Base


class PromptCategory(str, enum.Enum):
    MARKETING = "marketing"
    SALES = "sales"
    SUPPORT = "support"
    CONTENT = "content"
    DEVELOPMENT = "development"
    ANALYTICS = "analytics"
    OTHER = "other"


class PromptStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    PENDING = "pending"
    REJECTED = "rejected"


class ModelType(str, enum.Enum):
    GPT_4O = "gpt-4o"
    GPT_4 = "gpt-4"
    GPT_3_5_TURBO = "gpt-3.5-turbo"
    CLAUDE_3 = "claude-3"
    CUSTOM = "custom"


class Prompt(Base):
    __tablename__ = "prompts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    seller_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    title = Column(String(255), nullable=False, index=True)
    description = Column(Text)
    category = Column(Enum(PromptCategory), nullable=False, index=True)
    model_type = Column(Enum(ModelType), default=ModelType.GPT_4O, nullable=False)
    prompt_template = Column(Text, nullable=False)
    variables = Column(JSONB, default={})  # Store template variables
    example_input = Column(Text)
    example_output = Column(Text)
    price_per_use = Column(Numeric(10, 2), nullable=False)
    total_uses = Column(Integer, default=0)
    total_revenue = Column(Numeric(12, 2), default=0)
    average_rating = Column(Numeric(3, 2))
    rating_count = Column(Integer, default=0)
    status = Column(Enum(PromptStatus), default=PromptStatus.PENDING, nullable=False)
    version = Column(Integer, default=1)
    tags = Column(JSONB, default=[])  # Store tags as JSON array
    extra_metadata = Column(JSONB, default={})  # Additional metadata
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    # Relationships
    seller = relationship("User", back_populates="prompts")
    transactions = relationship(
        "Transaction", back_populates="prompt", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<Prompt {self.title}>"

    def to_dict(self):
        return {
            "id": str(self.id),
            "seller_id": str(self.seller_id),
            "title": self.title,
            "description": self.description,
            "category": self.category.value,
            "model_type": self.model_type.value,
            "price_per_use": float(self.price_per_use),
            "total_uses": self.total_uses,
            "average_rating": float(self.average_rating) if self.average_rating else None,
            "status": self.status.value,
            "tags": self.tags,
            "created_at": self.created_at.isoformat(),
        }

    def calculate_roi(self):
        """Calculate ROI metrics for the prompt"""
        if self.total_uses == 0:
            return {"roi": 0, "revenue_per_use": 0}

        revenue_per_use = float(self.total_revenue) / self.total_uses
        return {
            "roi": float(self.total_revenue),
            "revenue_per_use": revenue_per_use,
            "total_uses": self.total_uses,
        }