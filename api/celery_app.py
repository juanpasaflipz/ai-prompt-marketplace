"""
Celery configuration and application instance.

Handles background task processing for the AI Prompt Marketplace.
"""

from celery import Celery
from api.config import settings
import logging

logger = logging.getLogger(__name__)

# Create Celery instance
celery_app = Celery(
    "ai_prompt_marketplace",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["api.tasks"]  # Import task modules
)

# Configure Celery
celery_app.conf.update(
    # Task settings
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    
    # Task execution settings
    task_track_started=True,
    task_time_limit=30 * 60,  # 30 minutes
    task_soft_time_limit=25 * 60,  # 25 minutes
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    
    # Result backend settings
    result_expires=3600,  # 1 hour
    result_backend_transport_options={
        'visibility_timeout': 3600,
    },
    
    # Worker settings
    worker_disable_rate_limits=False,
    worker_send_task_events=True,
    
    # Queue configuration
    task_routes={
        'api.tasks.analytics.*': {'queue': 'analytics'},
        'api.tasks.email.*': {'queue': 'email'},
        'api.tasks.prompt.*': {'queue': 'prompt'},
        'api.tasks.payment.*': {'queue': 'payment'},
    },
    
    # Beat schedule for periodic tasks
    beat_schedule={
        # Flush analytics events every minute
        'flush-analytics': {
            'task': 'api.tasks.analytics.flush_analytics_events',
            'schedule': 60.0,  # Every 60 seconds
            'options': {'queue': 'analytics'}
        },
        
        # Clean expired sessions every hour
        'clean-sessions': {
            'task': 'api.tasks.maintenance.clean_expired_sessions',
            'schedule': 3600.0,  # Every hour
            'options': {'queue': 'maintenance'}
        },
        
        # Generate daily analytics report
        'daily-analytics-report': {
            'task': 'api.tasks.analytics.generate_daily_report',
            'schedule': 86400.0,  # Every 24 hours
            'options': {'queue': 'analytics'}
        },
        
        # Check subscription renewals
        'check-subscriptions': {
            'task': 'api.tasks.payment.check_subscription_renewals',
            'schedule': 3600.0,  # Every hour
            'options': {'queue': 'payment'}
        },
    },
)

# Task priorities
celery_app.conf.task_default_priority = 5
celery_app.conf.task_queue_max_priority = 10
celery_app.conf.worker_prefetch_multiplier = 1

# Error handling
celery_app.conf.task_reject_on_worker_lost = True
celery_app.conf.task_ignore_result = False


class CeleryConfig:
    """Configuration for Celery workers"""
    
    # Queues to process
    QUEUES = [
        'celery',      # Default queue
        'analytics',   # Analytics processing
        'email',       # Email sending
        'prompt',      # Prompt processing
        'payment',     # Payment processing
        'maintenance', # Maintenance tasks
    ]
    
    # Worker concurrency settings
    WORKER_CONCURRENCY = {
        'analytics': 4,
        'email': 2,
        'prompt': 4,
        'payment': 2,
        'maintenance': 1,
        'default': 4,
    }
    
    # Task rate limits (tasks per minute)
    TASK_RATE_LIMITS = {
        'api.tasks.email.send_email': '60/m',
        'api.tasks.analytics.track_event': '1000/m',
        'api.tasks.prompt.validate_prompt': '100/m',
    }


# Initialize Celery on import
logger.info("Celery app initialized with broker: %s", settings.redis_url)