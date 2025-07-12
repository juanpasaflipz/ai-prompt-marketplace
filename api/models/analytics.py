from sqlalchemy import Column, String, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
from api.database import Base


class AnalyticsEvent(Base):
    __tablename__ = "analytics_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    session_id = Column(String(255), nullable=True)  # For tracking user sessions
    event_type = Column(String(100), nullable=False, index=True)
    entity_type = Column(String(50), nullable=False)  # prompt, category, search, etc.
    entity_id = Column(String(255), nullable=True)
    event_metadata = Column(JSONB, default={})  # Flexible storage for event data
    ip_address = Column(String(45), nullable=True)  # Support IPv6
    user_agent = Column(String(500), nullable=True)
    referrer = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    # Relationships
    user = relationship("User", back_populates="analytics_events")

    # Indexes for performance
    __table_args__ = (
        Index("idx_analytics_user_event", "user_id", "event_type"),
        Index("idx_analytics_entity", "entity_type", "entity_id"),
        Index("idx_analytics_created_at", "created_at"),
        Index("idx_analytics_session", "session_id"),
    )

    def __repr__(self):
        return f"<AnalyticsEvent {self.event_type} - {self.entity_type}>"

    def to_dict(self):
        return {
            "id": str(self.id),
            "user_id": str(self.user_id) if self.user_id else None,
            "event_type": self.event_type,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "metadata": self.event_metadata,
            "created_at": self.created_at.isoformat(),
        }