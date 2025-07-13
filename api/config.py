from pydantic_settings import BaseSettings
from typing import List, Optional
from functools import lru_cache


class Settings(BaseSettings):
    # Application
    app_name: str = "AI Prompt Marketplace"
    app_version: str = "1.0.0"
    environment: str = "development"
    debug: bool = True
    secret_key: str

    # API Configuration
    api_v1_prefix: str = "/api/v1"
    allowed_origins: str = "http://localhost:3000,http://localhost:8000"
    app_base_url: str = "http://localhost:3000"  # Frontend URL for share links

    # Database
    database_url: str
    db_pool_size: int = 10
    db_max_overflow: int = 20

    # Redis & Caching
    redis_url: str = "redis://localhost:6379/0"
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_password: Optional[str] = None
    redis_db: int = 0
    redis_decode_responses: bool = True
    redis_max_connections: int = 10
    cache_enabled: bool = True
    cache_default_ttl: int = 3600  # 1 hour
    cache_prompt_ttl: int = 1800  # 30 minutes for prompts
    cache_user_ttl: int = 900  # 15 minutes for user data

    # Authentication
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # Stripe
    stripe_secret_key: str
    stripe_publishable_key: str
    stripe_webhook_secret: str
    stripe_price_id_basic: str = ""
    # Subscription price IDs
    stripe_basic_base_price_id: str = ""
    stripe_basic_usage_price_id: str = ""
    stripe_pro_base_price_id: str = ""
    stripe_pro_usage_price_id: str = ""
    stripe_enterprise_base_price_id: str = ""
    stripe_enterprise_usage_price_id: str = ""

    # OpenAI
    openai_api_key: str
    openai_model: str = "gpt-4o"

    # Email
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "noreply@promptmarketplace.com"

    # Monitoring
    sentry_dsn: str = ""
    log_level: str = "INFO"

    # Rate Limiting
    rate_limit_per_minute: int = 60
    rate_limit_per_hour: int = 1000

    # Analytics
    analytics_batch_size: int = 100
    analytics_flush_interval: int = 60

    # File Storage
    upload_max_size_mb: int = 10
    allowed_upload_extensions: str = ".txt,.json,.md"

    class Config:
        env_file = ".env"
        case_sensitive = False

    @property
    def allowed_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",")]
    
    @property
    def allowed_upload_extensions_list(self) -> List[str]:
        return [ext.strip() for ext in self.allowed_upload_extensions.split(",")]


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()