"""
Analytics background tasks.

Handles asynchronous analytics processing to avoid blocking API requests.
"""

from celery import shared_task
from celery.utils.log import get_task_logger
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from sqlalchemy import text, func
from sqlalchemy.orm import Session
import json

from api.database import get_db
from api.models.analytics import AnalyticsEvent
from api.models.prompt import Prompt
from api.models.transaction import Transaction
from api.models.user import User
from api.services.cache_service import get_cache_service
from api.config import settings

logger = get_task_logger(__name__)
cache = get_cache_service(
    host=settings.redis_host,
    port=settings.redis_port,
    password=settings.redis_password,
    db=settings.redis_db
)


@shared_task(bind=True, max_retries=3)
def flush_analytics_events(self):
    """
    Flush batched analytics events from cache to database.
    
    This task runs periodically to move events from the in-memory
    cache to persistent storage.
    """
    try:
        logger.info("Starting analytics flush task")
        
        # Get events from cache
        events_key = "analytics:events:batch"
        events_data = cache.get(events_key, serialization='pickle', default=[])
        
        if not events_data:
            logger.info("No analytics events to flush")
            return {"status": "success", "events_flushed": 0}
        
        # Clear the cache immediately to avoid processing same events
        cache.delete(events_key)
        
        # Process events
        db = next(get_db())
        events_created = 0
        
        try:
            for event_dict in events_data:
                # Parse metadata if it's a JSON string
                metadata = event_dict.get('metadata', {})
                if isinstance(metadata, str):
                    try:
                        metadata = json.loads(metadata)
                    except json.JSONDecodeError:
                        metadata = {}
                
                event = AnalyticsEvent(
                    user_id=event_dict.get('user_id'),
                    session_id=event_dict.get('session_id'),
                    event_type=event_dict['event_type'],
                    entity_type=event_dict.get('entity_type'),
                    entity_id=event_dict.get('entity_id'),
                    event_metadata=metadata,
                    ip_address=event_dict.get('ip_address'),
                    user_agent=event_dict.get('user_agent'),
                    referrer=event_dict.get('referrer'),
                    created_at=event_dict.get('created_at', datetime.utcnow())
                )
                db.add(event)
                events_created += 1
            
            db.commit()
            logger.info(f"Successfully flushed {events_created} analytics events")
            
        except Exception as e:
            db.rollback()
            logger.error(f"Error flushing analytics events: {e}")
            # Put events back in cache for retry
            cache.set(events_key, events_data, serialization='pickle')
            raise
        
        finally:
            db.close()
        
        return {"status": "success", "events_flushed": events_created}
        
    except Exception as e:
        logger.error(f"Analytics flush task failed: {e}")
        raise self.retry(exc=e, countdown=60)  # Retry after 1 minute


@shared_task(bind=True, max_retries=3)
def track_event_async(self, event_type: str, user_id: Optional[str] = None, 
                     metadata: Optional[Dict[str, Any]] = None):
    """
    Track an analytics event asynchronously.
    
    This is used for events that need immediate processing
    rather than batching.
    """
    try:
        db = next(get_db())
        
        event = AnalyticsEvent(
            event_type=event_type,
            user_id=user_id,
            event_metadata=metadata or {},
            created_at=datetime.utcnow()
        )
        
        db.add(event)
        db.commit()
        db.close()
        
        logger.info(f"Tracked event: {event_type} for user: {user_id}")
        return {"status": "success", "event_type": event_type}
        
    except Exception as e:
        logger.error(f"Error tracking event: {e}")
        raise self.retry(exc=e, countdown=30)


@shared_task(bind=True)
def generate_daily_report(self):
    """
    Generate daily analytics report.
    
    Aggregates analytics data and creates summary reports.
    """
    try:
        logger.info("Generating daily analytics report")
        
        db = next(get_db())
        
        # Calculate date range
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=1)
        
        # Get event counts by type
        event_counts = db.query(
            AnalyticsEvent.event_type,
            func.count(AnalyticsEvent.id).label('count')
        ).filter(
            AnalyticsEvent.created_at >= start_date,
            AnalyticsEvent.created_at < end_date
        ).group_by(AnalyticsEvent.event_type).all()
        
        # Get revenue data
        revenue_data = db.query(
            func.sum(Transaction.amount).label('total_revenue'),
            func.count(Transaction.id).label('transaction_count')
        ).filter(
            Transaction.created_at >= start_date,
            Transaction.created_at < end_date,
            Transaction.status == 'completed'
        ).first()
        
        # Get user statistics
        new_users = db.query(func.count(User.id)).filter(
            User.created_at >= start_date,
            User.created_at < end_date
        ).scalar()
        
        active_users = db.query(func.count(func.distinct(AnalyticsEvent.user_id))).filter(
            AnalyticsEvent.created_at >= start_date,
            AnalyticsEvent.created_at < end_date,
            AnalyticsEvent.user_id.isnot(None)
        ).scalar()
        
        # Get popular prompts
        popular_prompts = db.query(
            Prompt.id,
            Prompt.title,
            func.count(AnalyticsEvent.id).label('view_count')
        ).join(
            AnalyticsEvent,
            text("analytics_events.event_metadata->>'prompt_id' = CAST(prompts.id AS TEXT)")
        ).filter(
            AnalyticsEvent.event_type == 'prompt_viewed',
            AnalyticsEvent.created_at >= start_date,
            AnalyticsEvent.created_at < end_date
        ).group_by(
            Prompt.id, Prompt.title
        ).order_by(
            func.count(AnalyticsEvent.id).desc()
        ).limit(10).all()
        
        # Compile report
        report = {
            'date_range': {
                'start': start_date.isoformat(),
                'end': end_date.isoformat()
            },
            'event_summary': {event_type: count for event_type, count in event_counts},
            'revenue': {
                'total': float(revenue_data.total_revenue or 0),
                'transaction_count': revenue_data.transaction_count or 0
            },
            'users': {
                'new_users': new_users,
                'active_users': active_users
            },
            'popular_prompts': [
                {
                    'id': str(prompt.id),
                    'title': prompt.title,
                    'views': prompt.view_count
                }
                for prompt in popular_prompts
            ],
            'generated_at': datetime.utcnow().isoformat()
        }
        
        # Store report in cache
        report_key = f"analytics:daily_report:{start_date.date()}"
        cache.set(report_key, report, ttl=86400 * 7)  # Keep for 7 days
        
        db.close()
        
        logger.info(f"Daily report generated successfully for {start_date.date()}")
        return {"status": "success", "report_date": start_date.date().isoformat()}
        
    except Exception as e:
        logger.error(f"Error generating daily report: {e}")
        raise


@shared_task(bind=True)
def aggregate_prompt_stats(self, prompt_id: str):
    """
    Aggregate statistics for a specific prompt.
    
    Updates prompt performance metrics based on analytics data.
    """
    try:
        db = next(get_db())
        
        # Get the prompt
        prompt = db.query(Prompt).filter(Prompt.id == prompt_id).first()
        if not prompt:
            logger.warning(f"Prompt {prompt_id} not found")
            return {"status": "failed", "error": "Prompt not found"}
        
        # Calculate metrics
        # View count
        view_count = db.query(func.count(AnalyticsEvent.id)).filter(
            AnalyticsEvent.event_type == 'prompt_viewed',
            text("analytics_events.event_metadata->>'prompt_id' = :prompt_id")
        ).params(prompt_id=str(prompt_id)).scalar() or 0
        
        # Purchase count
        purchase_count = db.query(func.count(Transaction.id)).filter(
            Transaction.prompt_id == prompt_id,
            Transaction.status == 'completed'
        ).scalar() or 0
        
        # Total revenue
        total_revenue = db.query(func.sum(Transaction.amount)).filter(
            Transaction.prompt_id == prompt_id,
            Transaction.status == 'completed'
        ).scalar() or 0
        
        # Conversion rate
        conversion_rate = (purchase_count / view_count * 100) if view_count > 0 else 0
        
        # Update prompt metrics
        if prompt.extra_metadata is None:
            prompt.extra_metadata = {}
        
        prompt.extra_metadata['metrics'] = {
            'view_count': view_count,
            'purchase_count': purchase_count,
            'total_revenue': float(total_revenue),
            'conversion_rate': round(conversion_rate, 2),
            'last_updated': datetime.utcnow().isoformat()
        }
        
        db.commit()
        db.close()
        
        # Invalidate prompt cache
        cache.delete(f"prompt:detail:prompt_id={prompt_id}")
        
        logger.info(f"Updated stats for prompt {prompt_id}: views={view_count}, purchases={purchase_count}")
        
        return {
            "status": "success",
            "prompt_id": prompt_id,
            "metrics": prompt.extra_metadata['metrics']
        }
        
    except Exception as e:
        logger.error(f"Error aggregating prompt stats: {e}")
        raise


@shared_task(bind=True)
def clean_old_analytics(self, days_to_keep: int = 90):
    """
    Clean old analytics events to manage database size.
    
    Args:
        days_to_keep: Number of days of analytics to retain
    """
    try:
        cutoff_date = datetime.utcnow() - timedelta(days=days_to_keep)
        
        db = next(get_db())
        
        # Delete old events
        deleted_count = db.query(AnalyticsEvent).filter(
            AnalyticsEvent.created_at < cutoff_date
        ).delete()
        
        db.commit()
        db.close()
        
        logger.info(f"Deleted {deleted_count} analytics events older than {cutoff_date}")
        
        return {
            "status": "success",
            "deleted_count": deleted_count,
            "cutoff_date": cutoff_date.isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error cleaning old analytics: {e}")
        raise