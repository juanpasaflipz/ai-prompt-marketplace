from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from contextlib import asynccontextmanager
import logging
from api.config import settings
from api.routes import auth, prompts, marketplace, webhooks, api_keys
from api.middleware.analytics import AnalyticsMiddleware
from api.middleware.rate_limit import RateLimitMiddleware, limiter, add_rate_limit_handler
from api.middleware.api_key_auth import APIKeyAuthMiddleware
from api.database import engine, Base
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
import time

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events"""
    # Startup
    logger.info("Starting AI Prompt Marketplace API...")
    
    # Create database tables
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created/verified")
    
    yield
    
    # Shutdown
    logger.info("Shutting down API...")


# Create FastAPI instance
app = FastAPI(
    title="AI Prompt Marketplace",
    description="B2B Marketplace for Generative AI Prompts",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

# Add rate limiter to app state
app.state.limiter = limiter

# Add rate limit exceeded handler
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Add security middleware
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["*"]  # Configure based on environment
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add custom analytics middleware
app.add_middleware(AnalyticsMiddleware)

# Add rate limiting middleware
app.add_middleware(RateLimitMiddleware)

# Add API key authentication middleware
app.add_middleware(APIKeyAuthMiddleware)

# Add request timing middleware
@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    return response

# Include routers
app.include_router(auth.router, prefix=f"{settings.api_v1_prefix}/auth", tags=["Authentication"])
app.include_router(prompts.router, prefix=f"{settings.api_v1_prefix}/prompts", tags=["Prompts"])
app.include_router(marketplace.router, prefix=f"{settings.api_v1_prefix}/marketplace", tags=["Marketplace"])
app.include_router(webhooks.router, prefix=f"{settings.api_v1_prefix}/webhooks", tags=["Webhooks"])
app.include_router(api_keys.router, prefix=f"{settings.api_v1_prefix}/api-keys", tags=["API Keys"])
# app.include_router(analytics.router, prefix=f"{settings.api_v1_prefix}/analytics", tags=["Analytics"])

# Root endpoint
@app.get("/")
async def root():
    return {
        "message": "AI Prompt Marketplace API",
        "version": settings.app_version,
        "environment": settings.environment
    }

# Health check endpoint
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "version": settings.app_version,
        "environment": settings.environment
    }

# API info endpoint
@app.get(f"{settings.api_v1_prefix}")
async def api_info():
    return {
        "title": "AI Prompt Marketplace API",
        "version": "1.0",
        "description": "B2B marketplace for buying and selling optimized AI prompts",
        "endpoints": {
            "docs": "/docs",
            "redoc": "/redoc",
            "openapi": "/openapi.json"
        }
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )