"""
Rate limiting middleware for API endpoints.

Uses Redis-backed rate limiting with configurable limits per user/IP.
Supports both authenticated (per-user) and anonymous (per-IP) rate limiting.
"""

import time
from typing import Optional, Tuple, Dict, Any
from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
import logging

from api.config import settings
from api.services.cache_service import get_cache_service
from api.services.auth_service import AuthService

logger = logging.getLogger(__name__)

# Initialize cache service
cache = get_cache_service(
    host=settings.redis_host,
    port=settings.redis_port,
    password=settings.redis_password,
    db=settings.redis_db
)

# Auth service for user extraction
auth_service = AuthService()


def get_identifier(request: Request) -> str:
    """
    Get identifier for rate limiting.
    
    For authenticated users: user_{user_id}
    For anonymous users: ip_{ip_address}
    """
    # Try to get user from JWT token
    try:
        authorization = request.headers.get("Authorization", "")
        if authorization.startswith("Bearer "):
            token = authorization.split(" ")[1]
            payload = auth_service.decode_access_token(token)
            if payload and "sub" in payload:
                return f"user_{payload['sub']}"
    except Exception:
        pass
    
    # Fall back to IP address
    ip_address = get_remote_address(request)
    return f"ip_{ip_address}"


# Create limiter instance
limiter = Limiter(
    key_func=get_identifier,
    default_limits=[
        f"{settings.rate_limit_per_minute}/minute",
        f"{settings.rate_limit_per_hour}/hour"
    ],
    storage_uri=settings.redis_url,
    enabled=settings.cache_enabled  # Only enable if cache is enabled
)


class RateLimitMiddleware:
    """
    Custom rate limiting middleware with enhanced features.
    """
    
    def __init__(self):
        self.cache = cache
        self.enabled = settings.cache_enabled
        
    async def __call__(self, request: Request, call_next):
        """
        Process request with rate limiting.
        """
        if not self.enabled:
            # Skip rate limiting if disabled
            return await call_next(request)
        
        # Skip rate limiting for health checks and docs
        if request.url.path in ["/health", "/docs", "/redoc", "/openapi.json"]:
            return await call_next(request)
        
        identifier = get_identifier(request)
        
        # Check custom rate limits for specific endpoints
        custom_limit = self._get_custom_limit(request.url.path)
        if custom_limit:
            allowed, remaining, reset_time = await self._check_rate_limit(
                identifier, 
                request.url.path, 
                custom_limit
            )
            
            if not allowed:
                return self._rate_limit_exceeded_response(remaining, reset_time)
        
        # Add rate limit headers to response
        response = await call_next(request)
        
        # Add rate limit info to headers
        if custom_limit:
            response.headers["X-RateLimit-Limit"] = str(custom_limit["limit"])
            response.headers["X-RateLimit-Remaining"] = str(remaining)
            response.headers["X-RateLimit-Reset"] = str(reset_time)
        
        return response
    
    def _get_custom_limit(self, path: str) -> Optional[Dict[str, Any]]:
        """
        Get custom rate limits for specific endpoints.
        """
        custom_limits = {
            # Strict limits for auth endpoints
            "/api/v1/auth/login": {"limit": 10, "window": 300},  # 10 per 5 minutes
            "/api/v1/auth/register": {"limit": 5, "window": 300},  # 5 per 5 minutes
            "/api/v1/auth/forgot-password": {"limit": 3, "window": 600},  # 3 per 10 minutes
            
            # Moderate limits for payment endpoints
            "/api/v1/marketplace/purchase": {"limit": 20, "window": 60},  # 20 per minute
            "/api/v1/webhooks/stripe": {"limit": 100, "window": 60},  # 100 per minute
            
            # Generous limits for search
            "/api/v1/marketplace/search": {"limit": 100, "window": 60},  # 100 per minute
            
            # OpenAI endpoints (expensive)
            "/api/v1/prompts/test": {"limit": 10, "window": 60},  # 10 per minute
            "/api/v1/prompts/validate": {"limit": 20, "window": 60},  # 20 per minute
        }
        
        # Check if path matches any custom limit
        for pattern, limit_config in custom_limits.items():
            if path.startswith(pattern):
                return limit_config
        
        return None
    
    async def _check_rate_limit(
        self, 
        identifier: str, 
        endpoint: str, 
        limit_config: Dict[str, Any]
    ) -> Tuple[bool, int, int]:
        """
        Check if request is within rate limit.
        
        Returns:
            (allowed, remaining, reset_time)
        """
        key = f"rate_limit:{identifier}:{endpoint}"
        limit = limit_config["limit"]
        window = limit_config["window"]
        
        try:
            # Get current count
            current = self.cache.get(key, default=0)
            
            if current >= limit:
                # Calculate reset time
                ttl = self.cache.ttl(key)
                reset_time = int(time.time() + ttl) if ttl > 0 else int(time.time() + window)
                return False, 0, reset_time
            
            # Increment counter
            if current == 0:
                # First request, set with TTL
                self.cache.set(key, 1, ttl=window)
                remaining = limit - 1
            else:
                # Increment existing counter
                new_count = self.cache.incr(key)
                remaining = max(0, limit - new_count)
            
            # Calculate reset time
            ttl = self.cache.ttl(key)
            reset_time = int(time.time() + ttl) if ttl > 0 else int(time.time() + window)
            
            return True, remaining, reset_time
            
        except Exception as e:
            logger.error(f"Rate limit check failed: {e}")
            # Allow request on error
            return True, limit, int(time.time() + window)
    
    def _rate_limit_exceeded_response(self, remaining: int, reset_time: int) -> JSONResponse:
        """
        Create rate limit exceeded response.
        """
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={
                "detail": "Rate limit exceeded",
                "message": "Too many requests. Please try again later.",
                "retry_after": reset_time - int(time.time())
            },
            headers={
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(reset_time),
                "Retry-After": str(reset_time - int(time.time()))
            }
        )


def add_rate_limit_handler(app):
    """
    Add rate limit exceeded handler to FastAPI app.
    """
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# Decorator for custom rate limits on specific endpoints
def rate_limit(limit: str):
    """
    Decorator for applying custom rate limits to endpoints.
    
    Example:
        @rate_limit("5/minute")
        async def sensitive_endpoint():
            pass
    """
    return limiter.limit(limit)


# Export common rate limit decorators
auth_limit = rate_limit("10/5minute")  # For auth endpoints
payment_limit = rate_limit("20/minute")  # For payment endpoints
search_limit = rate_limit("100/minute")  # For search endpoints
ai_limit = rate_limit("10/minute")  # For AI/expensive endpoints