from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
import time
import uuid
import logging
from api.services.analytics_service import AnalyticsService, EventType

logger = logging.getLogger(__name__)


class AnalyticsMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self.analytics = AnalyticsService()
    
    async def dispatch(self, request: Request, call_next) -> Response:
        # Generate session ID if not present
        session_id = request.headers.get("X-Session-ID") or str(uuid.uuid4())
        
        # Track request start time
        start_time = time.time()
        
        # Call the actual endpoint
        response = await call_next(request)
        
        # Calculate response time
        process_time = time.time() - start_time
        
        # Add session ID to response headers
        response.headers["X-Session-ID"] = session_id
        
        # Track API usage analytics (non-blocking)
        try:
            # Only track successful requests to API endpoints
            if response.status_code < 400 and request.url.path.startswith("/api/"):
                # Extract user ID from JWT if available
                user_id = getattr(request.state, "user_id", None)
                
                # Track general API usage
                metadata = {
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "response_time_ms": round(process_time * 1000, 2),
                    "query_params": dict(request.query_params)
                }
                
                # Specific tracking for prompt views
                if "/prompts/" in request.url.path and request.method == "GET":
                    path_parts = request.url.path.split("/")
                    if len(path_parts) > 4:  # /api/v1/prompts/{id}
                        prompt_id = path_parts[4]
                        if self._is_valid_uuid(prompt_id):
                            self.analytics.track_event(
                                user_id=user_id,
                                event_type=EventType.PROMPT_VIEWED,
                                entity_type="prompt",
                                entity_id=prompt_id,
                                metadata=metadata,
                                session_id=session_id,
                                ip_address=request.client.host if request.client else None,
                                user_agent=request.headers.get("user-agent"),
                                referrer=request.headers.get("referer")
                            )
                
                # Track search queries
                elif "/marketplace/search" in request.url.path:
                    query = request.query_params.get("q")
                    if query:
                        self.analytics.track_event(
                            user_id=user_id,
                            event_type=EventType.SEARCH_PERFORMED,
                            entity_type="search",
                            entity_id=None,
                            metadata={**metadata, "query": query},
                            session_id=session_id,
                            ip_address=request.client.host if request.client else None,
                            user_agent=request.headers.get("user-agent")
                        )
                
                # Track category browsing
                elif "/marketplace/categories" in request.url.path:
                    category = request.query_params.get("category")
                    if category:
                        self.analytics.track_event(
                            user_id=user_id,
                            event_type=EventType.CATEGORY_BROWSED,
                            entity_type="category",
                            entity_id=category,
                            metadata=metadata,
                            session_id=session_id,
                            ip_address=request.client.host if request.client else None,
                            user_agent=request.headers.get("user-agent")
                        )
                        
        except Exception as e:
            # Don't let analytics errors break the request
            logger.error(f"Analytics tracking error: {e}")
        
        return response
    
    def _is_valid_uuid(self, value: str) -> bool:
        """Check if a string is a valid UUID"""
        try:
            uuid.UUID(value)
            return True
        except ValueError:
            return False