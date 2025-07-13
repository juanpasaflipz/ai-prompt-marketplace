"""
API Key model for programmatic access.

Supports API key authentication for enterprise users and integrations.
"""

from sqlalchemy import Column, String, DateTime, Boolean, Integer, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
import secrets
import hashlib

from api.database import Base


class APIKey(Base):
    __tablename__ = "api_keys"
    
    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # User relationship
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    user = relationship("User", back_populates="api_keys")
    
    # Key details
    name = Column(String(100), nullable=False)  # Human-friendly name
    key_hash = Column(String(255), unique=True, nullable=False)  # SHA-256 hash of key
    key_prefix = Column(String(8), nullable=False)  # First 8 chars for identification
    last_four = Column(String(4), nullable=False)  # Last 4 chars for identification
    
    # Permissions and limits
    permissions = Column(JSON, default=dict)  # JSON object with permission flags
    rate_limit = Column(Integer, default=1000)  # Requests per hour
    allowed_ips = Column(JSON, default=list)  # List of allowed IP addresses (empty = all)
    allowed_endpoints = Column(JSON, default=list)  # List of allowed endpoints (empty = all)
    
    # Usage tracking
    last_used_at = Column(DateTime, nullable=True)
    last_used_ip = Column(String(45), nullable=True)  # Supports IPv6
    total_requests = Column(Integer, default=0)
    
    # Status and lifecycle
    is_active = Column(Boolean, default=True)
    expires_at = Column(DateTime, nullable=True)  # Optional expiration
    revoked_at = Column(DateTime, nullable=True)
    revoked_reason = Column(String(255), nullable=True)
    
    # Metadata
    description = Column(String(500), nullable=True)
    tags = Column(JSON, default=list)  # For organization
    extra_metadata = Column(JSON, default=dict)  # Additional custom data
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Default permissions structure
    DEFAULT_PERMISSIONS = {
        "prompts": {
            "read": True,
            "write": False,
            "delete": False
        },
        "marketplace": {
            "browse": True,
            "purchase": True,
            "search": True
        },
        "analytics": {
            "read_own": True,
            "read_all": False
        },
        "users": {
            "read_own": True,
            "update_own": True,
            "read_all": False,
            "update_all": False
        }
    }
    
    @staticmethod
    def generate_key() -> str:
        """Generate a new API key."""
        # Generate 32 bytes of random data (256 bits)
        random_bytes = secrets.token_bytes(32)
        # Convert to base64-like string, but URL-safe
        key = secrets.token_urlsafe(32)
        # Add prefix for easy identification
        return f"sk_live_{key}"
    
    @staticmethod
    def hash_key(key: str) -> str:
        """Hash an API key for storage."""
        return hashlib.sha256(key.encode()).hexdigest()
    
    @classmethod
    def create_key(cls, user_id: str, name: str, **kwargs):
        """Create a new API key."""
        # Generate the actual key
        raw_key = cls.generate_key()
        
        # Extract prefix and suffix for identification
        key_prefix = raw_key[:8]
        last_four = raw_key[-4:]
        
        # Hash the key for storage
        key_hash = cls.hash_key(raw_key)
        
        # Create the API key object
        api_key = cls(
            user_id=user_id,
            name=name,
            key_hash=key_hash,
            key_prefix=key_prefix,
            last_four=last_four,
            permissions=kwargs.get('permissions', cls.DEFAULT_PERMISSIONS.copy()),
            **{k: v for k, v in kwargs.items() if k != 'permissions'}
        )
        
        # Return both the object and the raw key (only time raw key is available)
        return api_key, raw_key
    
    def verify_key(self, raw_key: str) -> bool:
        """Verify a raw API key against this key's hash."""
        return self.hash_key(raw_key) == self.key_hash
    
    def is_valid(self) -> bool:
        """Check if the API key is currently valid."""
        if not self.is_active:
            return False
        
        if self.revoked_at is not None:
            return False
        
        if self.expires_at and datetime.utcnow() > self.expires_at:
            return False
        
        return True
    
    def has_permission(self, resource: str, action: str) -> bool:
        """Check if the key has a specific permission."""
        if not self.permissions:
            return False
        
        resource_perms = self.permissions.get(resource, {})
        return resource_perms.get(action, False)
    
    def is_ip_allowed(self, ip_address: str) -> bool:
        """Check if an IP address is allowed to use this key."""
        if not self.allowed_ips:  # Empty list means all IPs allowed
            return True
        return ip_address in self.allowed_ips
    
    def is_endpoint_allowed(self, endpoint: str) -> bool:
        """Check if an endpoint is allowed for this key."""
        if not self.allowed_endpoints:  # Empty list means all endpoints allowed
            return True
        
        # Check exact matches and wildcards
        for allowed in self.allowed_endpoints:
            if allowed.endswith("*"):
                if endpoint.startswith(allowed[:-1]):
                    return True
            elif endpoint == allowed:
                return True
        
        return False
    
    def record_usage(self, ip_address: str):
        """Record usage of the API key."""
        self.last_used_at = datetime.utcnow()
        self.last_used_ip = ip_address
        self.total_requests += 1
    
    def revoke(self, reason: str = None):
        """Revoke the API key."""
        self.is_active = False
        self.revoked_at = datetime.utcnow()
        self.revoked_reason = reason
    
    def to_dict(self, include_sensitive: bool = False) -> dict:
        """Convert to dictionary representation."""
        data = {
            "id": str(self.id),
            "name": self.name,
            "key_prefix": self.key_prefix,
            "last_four": self.last_four,
            "permissions": self.permissions,
            "rate_limit": self.rate_limit,
            "is_active": self.is_active,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "last_used_at": self.last_used_at.isoformat() if self.last_used_at else None,
            "total_requests": self.total_requests,
            "created_at": self.created_at.isoformat(),
            "description": self.description,
            "tags": self.tags
        }
        
        if include_sensitive:
            data.update({
                "user_id": str(self.user_id),
                "allowed_ips": self.allowed_ips,
                "allowed_endpoints": self.allowed_endpoints,
                "last_used_ip": self.last_used_ip,
                "revoked_at": self.revoked_at.isoformat() if self.revoked_at else None,
                "revoked_reason": self.revoked_reason
            })
        
        return data
    
    def __repr__(self):
        return f"<APIKey {self.key_prefix}...{self.last_four} ({self.name})>"