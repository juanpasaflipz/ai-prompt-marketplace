"""
Pydantic schemas for API key management.
"""

from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Dict, Any
from datetime import datetime


class APIKeyPermissions(BaseModel):
    """Permissions structure for API keys."""
    
    prompts: Dict[str, bool] = Field(
        default={
            "read": True,
            "write": False,
            "delete": False
        }
    )
    marketplace: Dict[str, bool] = Field(
        default={
            "browse": True,
            "purchase": True,
            "search": True
        }
    )
    analytics: Dict[str, bool] = Field(
        default={
            "read_own": True,
            "read_all": False
        }
    )
    users: Dict[str, bool] = Field(
        default={
            "read_own": True,
            "update_own": True,
            "read_all": False,
            "update_all": False
        }
    )


class APIKeyCreate(BaseModel):
    """Schema for creating a new API key."""
    
    model_config = ConfigDict(protected_namespaces=())
    
    name: str = Field(..., min_length=1, max_length=100, description="Human-friendly name for the key")
    description: Optional[str] = Field(None, max_length=500, description="Description of key purpose")
    permissions: Optional[APIKeyPermissions] = Field(None, description="Custom permissions")
    expires_in_days: Optional[int] = Field(None, ge=1, le=365, description="Days until expiration")
    rate_limit: Optional[int] = Field(1000, ge=1, le=10000, description="Requests per hour")
    allowed_ips: Optional[List[str]] = Field(None, description="Whitelist of IP addresses")
    allowed_endpoints: Optional[List[str]] = Field(None, description="Whitelist of endpoints")
    tags: Optional[List[str]] = Field(None, description="Tags for organization")


class APIKeyUpdate(BaseModel):
    """Schema for updating an API key."""
    
    model_config = ConfigDict(protected_namespaces=())
    
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    permissions: Optional[APIKeyPermissions] = None
    expires_in_days: Optional[int] = Field(None, ge=1, le=365)
    rate_limit: Optional[int] = Field(None, ge=1, le=10000)
    allowed_ips: Optional[List[str]] = None
    allowed_endpoints: Optional[List[str]] = None
    tags: Optional[List[str]] = None


class APIKeyListResponse(BaseModel):
    """Schema for API key in list response (minimal info)."""
    
    model_config = ConfigDict(protected_namespaces=())
    
    id: str
    name: str
    key_prefix: str
    last_four: str
    is_active: bool
    expires_at: Optional[datetime]
    last_used_at: Optional[datetime]
    total_requests: int
    created_at: datetime
    description: Optional[str]
    tags: List[str]


class APIKeyResponse(BaseModel):
    """Schema for detailed API key response."""
    
    model_config = ConfigDict(protected_namespaces=())
    
    id: str
    user_id: str
    name: str
    key_prefix: str
    last_four: str
    permissions: Dict[str, Any]
    rate_limit: int
    is_active: bool
    expires_at: Optional[datetime]
    last_used_at: Optional[datetime]
    last_used_ip: Optional[str]
    total_requests: int
    created_at: datetime
    description: Optional[str]
    tags: List[str]
    allowed_ips: List[str]
    allowed_endpoints: List[str]
    revoked_at: Optional[datetime]
    revoked_reason: Optional[str]


class APIKeyDetailResponse(APIKeyResponse):
    """Schema for API key creation response (includes raw key)."""
    
    key: str = Field(..., description="The actual API key - only shown once")
    rotated_from: Optional[str] = Field(None, description="ID of previous key if rotated")


class APIKeyAuthRequest(BaseModel):
    """Schema for API key authentication."""
    
    api_key: str = Field(..., description="The API key to authenticate with")