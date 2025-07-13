from sqlalchemy import Column, String, Numeric, DateTime, ForeignKey, Enum, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
import enum
from api.database import Base


class TransactionStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    REFUNDED = "refunded"
    CANCELLED = "cancelled"


class TransactionType(str, enum.Enum):
    PROMPT_PURCHASE = "prompt_purchase"
    SUBSCRIPTION = "subscription"
    USAGE_FEE = "usage_fee"
    REFUND = "refund"


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    buyer_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    seller_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    prompt_id = Column(UUID(as_uuid=True), ForeignKey("prompts.id"), nullable=True)
    stripe_payment_id = Column(String(255), unique=True, nullable=True)
    stripe_payment_intent_id = Column(String(255), unique=True, nullable=True)
    amount = Column(Numeric(10, 2), nullable=False)
    currency = Column(String(3), default="USD", nullable=False)
    status = Column(
        Enum(TransactionStatus), default=TransactionStatus.PENDING, nullable=False
    )
    transaction_type = Column(
        Enum(TransactionType), default=TransactionType.PROMPT_PURCHASE, nullable=False
    )
    extra_metadata = Column(JSONB, default={})  # Store additional transaction data
    failure_reason = Column(Text, nullable=True)
    processed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    # Relationships
    buyer = relationship("User", back_populates="transactions")
    prompt = relationship("Prompt", back_populates="transactions")
    rating = relationship("PromptRating", back_populates="transaction", uselist=False)

    def __repr__(self):
        return f"<Transaction {self.id} - {self.status.value}>"

    def to_dict(self):
        return {
            "id": str(self.id),
            "buyer_id": str(self.buyer_id),
            "prompt_id": str(self.prompt_id) if self.prompt_id else None,
            "amount": float(self.amount),
            "currency": self.currency,
            "status": self.status.value,
            "transaction_type": self.transaction_type.value,
            "created_at": self.created_at.isoformat(),
            "processed_at": self.processed_at.isoformat() if self.processed_at else None,
        }