"""
API Key authentication middleware.

Handles authentication via API keys as an alternative to JWT tokens.
"""

from fastapi import Request, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime
import logging

from api.database import get_db
from api.models.api_key import APIKey
from api.models.user import User
from api.services.cache_service import get_cache_service
from api.config import settings

logger = logging.getLogger(__name__)

# Initialize cache
cache = get_cache_service(
    host=settings.redis_host,
    port=settings.redis_port,
    password=settings.redis_password,
    db=settings.redis_db
)


class APIKeyBearer(HTTPBearer):
    """
    Custom HTTPBearer for API key authentication.
    
    Expects API key in Authorization header as: Bearer sk_live_xxxxx
    """
    
    def __init__(self, auto_error: bool = True):
        super(APIKeyBearer, self).__init__(auto_error=auto_error)
    
    async def __call__(self, request: Request) -> Optional[str]:
        credentials: HTTPAuthorizationCredentials = await super(APIKeyBearer, self).__call__(request)
        
        if credentials:
            if not credentials.credentials.startswith("sk_"):
                if self.auto_error:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Invalid API key format"
                    )
                else:
                    return None
            
            return credentials.credentials
        
        return None


api_key_bearer = APIKeyBearer()


async def get_current_user_via_api_key(
    api_key: str = api_key_bearer,
    request: Request = None
) -> User:
    """
    Authenticate user via API key.
    
    Returns the User object associated with the API key.
    """
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key required"
        )
    
    # Check cache first
    cache_key = f"api_key:user:{APIKey.hash_key(api_key)}"
    cached_user_id = cache.get(cache_key)
    
    db = next(get_db())
    
    try:
        if cached_user_id:
            # Get user from cache hit
            user = db.query(User).filter(User.id == cached_user_id).first()
            if user and user.is_active == "true":
                # Update API key usage stats asynchronously
                _update_api_key_usage(db, api_key, request)
                return user
        
        # Look up API key
        key_hash = APIKey.hash_key(api_key)
        api_key_obj = db.query(APIKey).filter(
            APIKey.key_hash == key_hash
        ).first()
        
        if not api_key_obj:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key"
            )
        
        # Validate API key
        if not api_key_obj.is_valid():
            if api_key_obj.revoked_at:
                detail = "API key has been revoked"
            elif api_key_obj.expires_at and api_key_obj.expires_at < datetime.utcnow():
                detail = "API key has expired"
            else:
                detail = "API key is not active"
            
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=detail
            )
        
        # Check IP restrictions
        if request and api_key_obj.allowed_ips:
            client_ip = request.client.host
            if not api_key_obj.is_ip_allowed(client_ip):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied from this IP address"
                )
        
        # Check endpoint restrictions
        if request and api_key_obj.allowed_endpoints:
            endpoint = request.url.path
            if not api_key_obj.is_endpoint_allowed(endpoint):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied to this endpoint"
                )
        
        # Get associated user
        user = db.query(User).filter(User.id == api_key_obj.user_id).first()
        
        if not user or user.is_active != "true":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User account is not active"
            )
        
        # Cache the user ID for this API key
        cache.set(cache_key, str(user.id), ttl=300)  # Cache for 5 minutes
        
        # Update usage stats
        _update_api_key_usage(db, api_key, request, api_key_obj)
        
        # Add API key to request state for downstream use
        if request:
            request.state.api_key = api_key_obj
        
        return user
        
    finally:
        db.close()


def _update_api_key_usage(
    db: Session,
    api_key: str,
    request: Optional[Request] = None,
    api_key_obj: Optional[APIKey] = None
):
    """
    Update API key usage statistics.
    
    This is done asynchronously to not block the request.
    """
    try:
        if not api_key_obj:
            key_hash = APIKey.hash_key(api_key)
            api_key_obj = db.query(APIKey).filter(
                APIKey.key_hash == key_hash
            ).first()
        
        if api_key_obj:
            client_ip = request.client.host if request else None
            api_key_obj.record_usage(client_ip)
            db.commit()
    except Exception as e:
        logger.error(f"Error updating API key usage: {e}")
        db.rollback()


class APIKeyAuthMiddleware:
    """
    Middleware to check API key authentication for specific routes.
    """
    
    def __init__(self):
        self.protected_prefixes = [
            "/api/v1/prompts",
            "/api/v1/marketplace",
            "/api/v1/analytics"
        ]
        self.excluded_paths = [
            "/api/v1/auth",
            "/health",
            "/docs",
            "/redoc",
            "/openapi.json"
        ]
    
    async def __call__(self, request: Request, call_next):
        """
        Check if request needs API key authentication.
        """
        path = request.url.path
        
        # Skip excluded paths
        if any(path.startswith(excluded) for excluded in self.excluded_paths):
            return await call_next(request)
        
        # Check if path needs protection
        needs_auth = any(path.startswith(prefix) for prefix in self.protected_prefixes)
        
        if needs_auth:
            # Check for API key in header
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer sk_"):
                try:
                    # Validate API key
                    api_key = auth_header.split(" ")[1]
                    user = await get_current_user_via_api_key(api_key, request)
                    request.state.user = user
                except HTTPException:
                    # Let it fall through to JWT auth
                    pass
        
        return await call_next(request)


def check_api_key_permission(permission_resource: str, permission_action: str):
    """
    Dependency to check if API key has specific permission.
    
    Usage:
        @router.get("/admin-only", dependencies=[Depends(check_api_key_permission("users", "read_all"))])
    """
    
    def permission_checker(request: Request):
        if hasattr(request.state, "api_key"):
            api_key = request.state.api_key
            if not api_key.has_permission(permission_resource, permission_action):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"API key lacks permission: {permission_resource}:{permission_action}"
                )
        # If not using API key auth, skip permission check (JWT auth will handle it)
        return True
    
    return permission_checker