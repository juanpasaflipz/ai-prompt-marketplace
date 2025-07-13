from enum import Enum
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from api.models.analytics import AnalyticsEvent
from api.database import get_db
from api.config import settings
from api.services.cache_service import get_cache_service
from api.tasks.analytics import flush_analytics_events
import json
import logging
import threading

logger = logging.getLogger(__name__)


class EventType(str, Enum):
    # User Events
    USER_REGISTERED = "user_registered"
    USER_LOGIN = "user_login"
    USER_UPGRADED = "user_upgraded"
    USER_LOGOUT = "user_logout"
    
    # Prompt Events
    PROMPT_VIEWED = "prompt_viewed"
    PROMPT_CLICKED = "prompt_clicked"
    PROMPT_PURCHASED = "prompt_purchased"
    PROMPT_USED = "prompt_used"
    PROMPT_RATED = "prompt_rated"
    PROMPT_CREATED = "prompt_created"
    PROMPT_UPDATED = "prompt_updated"
    PROMPT_DELETED = "prompt_deleted"
    
    # Search Events
    SEARCH_PERFORMED = "search_performed"
    SEARCH_RESULT_CLICKED = "search_result_clicked"
    
    # Category Events
    CATEGORY_BROWSED = "category_browsed"
    
    # Transaction Events
    PAYMENT_INITIATED = "payment_initiated"
    PAYMENT_COMPLETED = "payment_completed"
    PAYMENT_FAILED = "payment_failed"
    PAYMENT_REFUNDED = "payment_refunded"


class AnalyticsService:
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
            
        # Initialize cache service
        self.cache = get_cache_service(
            host=settings.redis_host,
            port=settings.redis_port,
            password=settings.redis_password,
            db=settings.redis_db
        )
        self.events_key = "analytics:events:batch"
        self.batch_size = settings.analytics_batch_size
        self.flush_interval = settings.analytics_flush_interval
        self._initialized = True
    
    def track_event(
        self,
        user_id: Optional[str],
        event_type: EventType,
        entity_type: str,
        entity_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        referrer: Optional[str] = None
    ):
        """Track analytics event with batching"""
        event = {
            "user_id": user_id,
            "session_id": session_id,
            "event_type": event_type.value,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "metadata": json.dumps(metadata or {}),
            "ip_address": ip_address,
            "user_agent": user_agent,
            "referrer": referrer,
            "created_at": datetime.utcnow()
        }
        
        # Get current batch from cache
        with self._lock:
            current_batch = self.cache.get(self.events_key, serialization='pickle', default=[])
            current_batch.append(event)
            
            # Save updated batch to cache
            self.cache.set(self.events_key, current_batch, serialization='pickle')
            
            # Trigger flush if batch size reached
            if len(current_batch) >= self.batch_size:
                self._flush_events()
    
    def _flush_events(self):
        """Trigger Celery task to flush events to database"""
        try:
            # Trigger the Celery task
            flush_analytics_events.delay()
            logger.info("Triggered analytics flush task")
        except Exception as e:
            logger.error(f"Error triggering analytics flush task: {e}")
    
    def flush_events_now(self):
        """Manually trigger event flush (useful for graceful shutdown)"""
        try:
            # Check if there are events to flush
            current_batch = self.cache.get(self.events_key, serialization='pickle', default=[])
            if current_batch:
                flush_analytics_events.delay()
                logger.info(f"Manually triggered flush for {len(current_batch)} events")
                return True
            return False
        except Exception as e:
            logger.error(f"Error in manual flush: {e}")
            return False
    
    def get_queue_size(self) -> int:
        """Get the current number of events in the queue"""
        try:
            current_batch = self.cache.get(self.events_key, serialization='pickle', default=[])
            return len(current_batch)
        except Exception as e:
            logger.error(f"Error getting queue size: {e}")
            return 0
    
    def get_prompt_analytics(self, prompt_id: str, days: int = 30, db: Session = None) -> Dict[str, Any]:
        """Get comprehensive analytics for a prompt"""
        if not db:
            db = next(get_db())
            close_db = True
        else:
            close_db = False
            
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=days)
            
            # Query different metrics
            metrics = {
                "period_days": days,
                "prompt_id": prompt_id
            }
            
            # Total views
            views_count = db.query(func.count(AnalyticsEvent.id)).filter(
                and_(
                    AnalyticsEvent.entity_id == prompt_id,
                    AnalyticsEvent.event_type == EventType.PROMPT_VIEWED.value,
                    AnalyticsEvent.created_at >= cutoff_date
                )
            ).scalar() or 0
            
            # Total clicks
            clicks_count = db.query(func.count(AnalyticsEvent.id)).filter(
                and_(
                    AnalyticsEvent.entity_id == prompt_id,
                    AnalyticsEvent.event_type == EventType.PROMPT_CLICKED.value,
                    AnalyticsEvent.created_at >= cutoff_date
                )
            ).scalar() or 0
            
            # Total purchases
            purchases_count = db.query(func.count(AnalyticsEvent.id)).filter(
                and_(
                    AnalyticsEvent.entity_id == prompt_id,
                    AnalyticsEvent.event_type == EventType.PROMPT_PURCHASED.value,
                    AnalyticsEvent.created_at >= cutoff_date
                )
            ).scalar() or 0
            
            # Calculate conversion rates
            metrics["views"] = views_count
            metrics["clicks"] = clicks_count
            metrics["purchases"] = purchases_count
            metrics["view_to_click_rate"] = (clicks_count / views_count * 100) if views_count > 0 else 0
            metrics["click_to_purchase_rate"] = (purchases_count / clicks_count * 100) if clicks_count > 0 else 0
            metrics["overall_conversion_rate"] = (purchases_count / views_count * 100) if views_count > 0 else 0
            
            # Views timeline
            views_timeline = db.query(
                func.date_trunc('day', AnalyticsEvent.created_at).label('date'),
                func.count(AnalyticsEvent.id).label('count')
            ).filter(
                and_(
                    AnalyticsEvent.entity_id == prompt_id,
                    AnalyticsEvent.event_type == EventType.PROMPT_VIEWED.value,
                    AnalyticsEvent.created_at >= cutoff_date
                )
            ).group_by(
                func.date_trunc('day', AnalyticsEvent.created_at)
            ).order_by('date').all()
            
            metrics['views_timeline'] = [
                {"date": row.date.isoformat(), "count": row.count}
                for row in views_timeline
            ]
            
            # Unique users
            unique_users = db.query(func.count(func.distinct(AnalyticsEvent.user_id))).filter(
                and_(
                    AnalyticsEvent.entity_id == prompt_id,
                    AnalyticsEvent.event_type.in_([
                        EventType.PROMPT_VIEWED.value,
                        EventType.PROMPT_CLICKED.value,
                        EventType.PROMPT_PURCHASED.value
                    ]),
                    AnalyticsEvent.created_at >= cutoff_date
                )
            ).scalar() or 0
            
            metrics["unique_users"] = unique_users
            
            return metrics
            
        finally:
            if close_db:
                db.close()
    
    def get_user_analytics(self, user_id: str, days: int = 30, db: Session = None) -> Dict[str, Any]:
        """Get analytics for a specific user"""
        if not db:
            db = next(get_db())
            close_db = True
        else:
            close_db = False
            
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=days)
            
            # Get event counts by type
            event_counts = db.query(
                AnalyticsEvent.event_type,
                func.count(AnalyticsEvent.id).label('count')
            ).filter(
                and_(
                    AnalyticsEvent.user_id == user_id,
                    AnalyticsEvent.created_at >= cutoff_date
                )
            ).group_by(AnalyticsEvent.event_type).all()
            
            metrics = {
                "user_id": user_id,
                "period_days": days,
                "event_counts": {row.event_type: row.count for row in event_counts},
                "total_events": sum(row.count for row in event_counts)
            }
            
            return metrics
            
        finally:
            if close_db:
                db.close()
    
    def get_marketplace_analytics(self, days: int = 30, db: Session = None) -> Dict[str, Any]:
        """Get overall marketplace analytics"""
        if not db:
            db = next(get_db())
            close_db = True
        else:
            close_db = False
            
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=days)
            
            # Top categories
            category_views = db.query(
                AnalyticsEvent.metadata['category'].astext.label('category'),
                func.count(AnalyticsEvent.id).label('views')
            ).filter(
                and_(
                    AnalyticsEvent.event_type == EventType.CATEGORY_BROWSED.value,
                    AnalyticsEvent.created_at >= cutoff_date
                )
            ).group_by(
                AnalyticsEvent.metadata['category'].astext
            ).order_by(func.count(AnalyticsEvent.id).desc()).limit(10).all()
            
            # Search queries
            search_queries = db.query(
                AnalyticsEvent.metadata['query'].astext.label('query'),
                func.count(AnalyticsEvent.id).label('count')
            ).filter(
                and_(
                    AnalyticsEvent.event_type == EventType.SEARCH_PERFORMED.value,
                    AnalyticsEvent.created_at >= cutoff_date
                )
            ).group_by(
                AnalyticsEvent.metadata['query'].astext
            ).order_by(func.count(AnalyticsEvent.id).desc()).limit(20).all()
            
            metrics = {
                "period_days": days,
                "top_categories": [
                    {"category": row.category, "views": row.views}
                    for row in category_views
                ],
                "top_searches": [
                    {"query": row.query, "count": row.count}
                    for row in search_queries
                ]
            }
            
            return metrics
            
        finally:
            if close_db:
                db.close()


# Global instance
analytics_service = AnalyticsService()