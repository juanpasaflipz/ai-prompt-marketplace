from sqlalchemy import Column, String, Integer, Numeric, Text, DateTime, ForeignKey, Enum, Boolean
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
    category = Column(String(50), nullable=False, index=True)  # Changed from Enum to String
    model_type = Column(Enum(ModelType), default=ModelType.GPT_4O, nullable=False)
    prompt_template = Column(Text, nullable=False)
    variables = Column(JSONB, default={})  # Store template variables
    example_input = Column(Text)
    example_output = Column(Text)
    price = Column(Numeric(10, 2), nullable=False)  # Renamed from price_per_use
    subcategory = Column(String(100), nullable=True)  # Added subcategory
    total_sales = Column(Integer, default=0)  # Renamed from total_uses
    total_revenue = Column(Numeric(12, 2), default=0)
    rating_average = Column(Numeric(3, 2))  # Renamed from average_rating
    rating_count = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)  # Changed from status enum
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
    shares = relationship("PromptShare", back_populates="prompt", cascade="all, delete-orphan")
    ratings = relationship("PromptRating", back_populates="prompt", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Prompt {self.title}>"

    def to_dict(self):
        return {
            "id": str(self.id),
            "seller_id": str(self.seller_id),
            "title": self.title,
            "description": self.description,
            "category": self.category,
            "model_type": self.model_type.value,
            "price": float(self.price),
            "total_sales": self.total_sales,
            "rating_average": float(self.rating_average) if self.rating_average else None,
            "is_active": self.is_active,
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