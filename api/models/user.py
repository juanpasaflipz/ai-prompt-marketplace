from sqlalchemy import Column, String, DateTime, Enum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
import enum
from api.database import Base


class UserRole(str, enum.Enum):
    BUYER = "buyer"
    SELLER = "seller"
    ADMIN = "admin"


class SubscriptionStatus(str, enum.Enum):
    TRIAL = "trial"
    ACTIVE = "active"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    company_name = Column(String(255), nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(Enum(UserRole), default=UserRole.BUYER, nullable=False)
    stripe_customer_id = Column(String(255), unique=True, nullable=True)
    subscription_status = Column(
        Enum(SubscriptionStatus), default=SubscriptionStatus.TRIAL, nullable=False
    )
    subscription_plan = Column(String(50), nullable=True)  # basic, professional, enterprise
    subscription_id = Column(String(255), nullable=True)  # Stripe subscription ID
    subscription_usage_item_id = Column(String(255), nullable=True)  # For metered billing
    is_active = Column(String, default="true")
    full_name = Column(String(255), nullable=True)  # Added for seller profiles
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    # Relationships
    prompts = relationship("Prompt", back_populates="seller", cascade="all, delete-orphan")
    transactions = relationship(
        "Transaction", back_populates="buyer", cascade="all, delete-orphan"
    )
    analytics_events = relationship(
        "AnalyticsEvent", back_populates="user", cascade="all, delete-orphan"
    )
    api_keys = relationship(
        "APIKey", back_populates="user", cascade="all, delete-orphan"
    )
    shared_prompts = relationship(
        "PromptShare", back_populates="user", cascade="all, delete-orphan"
    )
    ratings_given = relationship(
        "PromptRating", back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<User {self.email}>"

    def to_dict(self):
        return {
            "id": str(self.id),
            "email": self.email,
            "company_name": self.company_name,
            "role": self.role.value,
            "subscription_status": self.subscription_status.value,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat(),
        }