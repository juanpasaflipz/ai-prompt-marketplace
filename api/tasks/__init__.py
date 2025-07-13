"""
Background tasks for AI Prompt Marketplace.

This module contains all Celery tasks organized by functionality.
"""

from api.tasks.analytics import *
from api.tasks.email import *
from api.tasks.prompt import *
from api.tasks.payment import *
from api.tasks.maintenance import *

__all__ = [
    # Analytics tasks
    'flush_analytics_events',
    'track_event_async',
    'generate_daily_report',
    'aggregate_prompt_stats',
    
    # Email tasks
    'send_email',
    'send_welcome_email',
    'send_purchase_confirmation',
    'send_password_reset',
    
    # Prompt tasks
    'validate_prompt_async',
    'test_prompt_async',
    'generate_prompt_preview',
    'update_prompt_metrics',
    
    # Payment tasks
    'process_payment_webhook',
    'check_subscription_renewals',
    'retry_failed_payments',
    
    # Maintenance tasks
    'clean_expired_sessions',
    'clean_old_analytics',
    'optimize_database',
]