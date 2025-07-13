"""
Advanced analytics funnel tracking and conversion optimization.

This module provides sophisticated funnel analysis, user behavior tracking,
and conversion rate optimization features.
"""

from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_, distinct, case
from collections import defaultdict
import json
import logging

from api.models.analytics import AnalyticsEvent
from api.models.user import User
from api.models.prompt import Prompt
from api.models.transaction import Transaction
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


class FunnelAnalytics:
    """
    Advanced funnel analytics for tracking user conversion paths.
    """
    
    # Define standard funnels
    PURCHASE_FUNNEL = [
        "prompt_viewed",
        "prompt_clicked", 
        "prompt_add_to_cart",
        "checkout_started",
        "payment_initiated",
        "prompt_purchased"
    ]
    
    SELLER_FUNNEL = [
        "seller_onboarding_started",
        "first_prompt_created",
        "prompt_published",
        "first_sale_completed",
        "seller_milestone_10_sales"
    ]
    
    SUBSCRIPTION_FUNNEL = [
        "subscription_page_viewed",
        "plan_selected",
        "payment_details_entered",
        "subscription_started",
        "subscription_first_renewal"
    ]
    
    @staticmethod
    def track_funnel_event(
        db: Session,
        user_id: str,
        event_type: str,
        funnel_name: str,
        session_id: str,
        metadata: Optional[Dict] = None
    ):
        """
        Track a funnel event with session correlation.
        """
        event_data = {
            "funnel_name": funnel_name,
            "funnel_step": event_type,
            "session_id": session_id,
            **(metadata or {})
        }
        
        event = AnalyticsEvent(
            user_id=user_id,
            event_type=event_type,
            event_category="funnel",
            metadata=event_data,
            session_id=session_id
        )
        
        db.add(event)
        
        # Update funnel cache for real-time tracking
        cache_key = f"funnel:{funnel_name}:{session_id}"
        funnel_data = cache.get(cache_key, default={})
        funnel_data[event_type] = datetime.utcnow().isoformat()
        cache.set(cache_key, funnel_data, ttl=3600)  # 1 hour TTL
    
    @staticmethod
    def calculate_funnel_conversion(
        db: Session,
        funnel_steps: List[str],
        start_date: datetime,
        end_date: datetime,
        user_segment: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Calculate conversion rates for each step in a funnel.
        """
        results = {
            "funnel_name": funnel_steps[0].split("_")[0],
            "date_range": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat()
            },
            "steps": [],
            "overall_conversion": 0,
            "average_time_to_convert": None,
            "drop_off_analysis": []
        }
        
        # Build base query
        base_query = db.query(AnalyticsEvent).filter(
            and_(
                AnalyticsEvent.created_at >= start_date,
                AnalyticsEvent.created_at <= end_date
            )
        )
        
        # Apply user segment filters if provided
        if user_segment:
            # Implementation would filter based on user attributes
            pass
        
        # Calculate users at each step
        step_users = {}
        for i, step in enumerate(funnel_steps):
            users_at_step = base_query.filter(
                AnalyticsEvent.event_type == step
            ).distinct(AnalyticsEvent.user_id).count()
            
            step_users[step] = users_at_step
            
            # Calculate conversion from previous step
            if i == 0:
                conversion_rate = 100.0
                drop_off_rate = 0.0
            else:
                prev_step = funnel_steps[i-1]
                if step_users[prev_step] > 0:
                    conversion_rate = (users_at_step / step_users[prev_step]) * 100
                    drop_off_rate = 100 - conversion_rate
                else:
                    conversion_rate = 0.0
                    drop_off_rate = 100.0
            
            results["steps"].append({
                "step_name": step,
                "users": users_at_step,
                "conversion_rate": round(conversion_rate, 2),
                "drop_off_rate": round(drop_off_rate, 2)
            })
            
            if i > 0 and drop_off_rate > 50:  # High drop-off threshold
                results["drop_off_analysis"].append({
                    "from_step": prev_step,
                    "to_step": step,
                    "drop_off_rate": round(drop_off_rate, 2),
                    "severity": "high" if drop_off_rate > 70 else "medium"
                })
        
        # Calculate overall conversion
        if step_users[funnel_steps[0]] > 0:
            results["overall_conversion"] = round(
                (step_users[funnel_steps[-1]] / step_users[funnel_steps[0]]) * 100, 
                2
            )
        
        # Calculate average time to convert
        complete_sessions = base_query.filter(
            AnalyticsEvent.event_type == funnel_steps[-1]
        ).all()
        
        if complete_sessions:
            conversion_times = []
            for session in complete_sessions:
                start_event = base_query.filter(
                    and_(
                        AnalyticsEvent.session_id == session.session_id,
                        AnalyticsEvent.event_type == funnel_steps[0]
                    )
                ).first()
                
                if start_event:
                    time_diff = session.created_at - start_event.created_at
                    conversion_times.append(time_diff.total_seconds())
            
            if conversion_times:
                avg_seconds = sum(conversion_times) / len(conversion_times)
                results["average_time_to_convert"] = {
                    "seconds": round(avg_seconds),
                    "formatted": str(timedelta(seconds=int(avg_seconds)))
                }
        
        return results
    
    @staticmethod
    def get_abandoned_carts(
        db: Session,
        time_threshold: timedelta = timedelta(hours=1)
    ) -> List[Dict[str, Any]]:
        """
        Identify abandoned cart sessions.
        """
        cutoff_time = datetime.utcnow() - time_threshold
        
        # Find sessions with cart additions but no purchases
        cart_sessions = db.query(
            AnalyticsEvent.session_id,
            AnalyticsEvent.user_id,
            func.max(AnalyticsEvent.created_at).label("last_activity")
        ).filter(
            and_(
                AnalyticsEvent.event_type == "prompt_add_to_cart",
                AnalyticsEvent.created_at < cutoff_time
            )
        ).group_by(
            AnalyticsEvent.session_id,
            AnalyticsEvent.user_id
        ).all()
        
        abandoned_carts = []
        for session in cart_sessions:
            # Check if purchase was completed
            purchase = db.query(AnalyticsEvent).filter(
                and_(
                    AnalyticsEvent.session_id == session.session_id,
                    AnalyticsEvent.event_type == "prompt_purchased"
                )
            ).first()
            
            if not purchase:
                # Get cart details
                cart_events = db.query(AnalyticsEvent).filter(
                    and_(
                        AnalyticsEvent.session_id == session.session_id,
                        AnalyticsEvent.event_type == "prompt_add_to_cart"
                    )
                ).all()
                
                cart_value = sum(
                    float(event.metadata.get("price", 0)) 
                    for event in cart_events
                )
                
                abandoned_carts.append({
                    "session_id": session.session_id,
                    "user_id": session.user_id,
                    "last_activity": session.last_activity.isoformat(),
                    "cart_value": cart_value,
                    "items_count": len(cart_events),
                    "abandonment_duration": str(datetime.utcnow() - session.last_activity)
                })
        
        return abandoned_carts
    
    @staticmethod
    def calculate_cohort_retention(
        db: Session,
        cohort_date: datetime,
        retention_periods: List[int] = [1, 7, 14, 30, 60, 90]
    ) -> Dict[str, Any]:
        """
        Calculate user retention for a cohort.
        """
        # Get cohort users (users who joined on cohort_date)
        cohort_start = cohort_date.replace(hour=0, minute=0, second=0)
        cohort_end = cohort_start + timedelta(days=1)
        
        cohort_users = db.query(User.id).filter(
            and_(
                User.created_at >= cohort_start,
                User.created_at < cohort_end
            )
        ).all()
        
        cohort_size = len(cohort_users)
        cohort_user_ids = [user.id for user in cohort_users]
        
        retention_data = {
            "cohort_date": cohort_date.date().isoformat(),
            "cohort_size": cohort_size,
            "retention_periods": []
        }
        
        for period in retention_periods:
            period_start = cohort_date + timedelta(days=period)
            period_end = period_start + timedelta(days=1)
            
            # Count active users in this period
            active_users = db.query(
                distinct(AnalyticsEvent.user_id)
            ).filter(
                and_(
                    AnalyticsEvent.user_id.in_(cohort_user_ids),
                    AnalyticsEvent.created_at >= period_start,
                    AnalyticsEvent.created_at < period_end
                )
            ).count()
            
            retention_rate = (active_users / cohort_size * 100) if cohort_size > 0 else 0
            
            retention_data["retention_periods"].append({
                "day": period,
                "active_users": active_users,
                "retention_rate": round(retention_rate, 2)
            })
        
        return retention_data
    
    @staticmethod
    def calculate_user_lifetime_value(
        db: Session,
        user_id: str,
        include_projections: bool = True
    ) -> Dict[str, Any]:
        """
        Calculate and project user lifetime value.
        """
        # Get all user transactions
        transactions = db.query(Transaction).filter(
            Transaction.buyer_id == user_id
        ).all()
        
        if not transactions:
            return {
                "user_id": user_id,
                "current_ltv": 0,
                "transaction_count": 0,
                "average_order_value": 0,
                "projected_ltv": 0
            }
        
        # Calculate current LTV
        total_revenue = sum(t.amount for t in transactions)
        transaction_count = len(transactions)
        avg_order_value = total_revenue / transaction_count
        
        # Calculate purchase frequency
        if transaction_count > 1:
            first_purchase = min(t.created_at for t in transactions)
            last_purchase = max(t.created_at for t in transactions)
            days_active = (last_purchase - first_purchase).days or 1
            purchase_frequency = transaction_count / days_active * 30  # Monthly frequency
        else:
            purchase_frequency = 0.5  # Assume bi-monthly for single purchase
        
        ltv_data = {
            "user_id": user_id,
            "current_ltv": float(total_revenue),
            "transaction_count": transaction_count,
            "average_order_value": float(avg_order_value),
            "purchase_frequency_monthly": round(purchase_frequency, 2)
        }
        
        if include_projections:
            # Simple LTV projection (AOV * Purchase Frequency * Expected Lifetime)
            expected_lifetime_months = 24  # 2 years
            projected_ltv = avg_order_value * purchase_frequency * expected_lifetime_months
            
            ltv_data["projected_ltv"] = round(float(projected_ltv), 2)
            ltv_data["projection_months"] = expected_lifetime_months
        
        return ltv_data


class UserBehaviorAnalytics:
    """
    Advanced user behavior tracking and analysis.
    """
    
    @staticmethod
    def track_user_journey(
        db: Session,
        user_id: str,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get complete user journey with all touchpoints.
        """
        events = db.query(AnalyticsEvent).filter(
            AnalyticsEvent.user_id == user_id
        ).order_by(
            AnalyticsEvent.created_at.desc()
        ).limit(limit).all()
        
        journey = []
        for event in events:
            journey.append({
                "timestamp": event.created_at.isoformat(),
                "event_type": event.event_type,
                "category": event.event_category,
                "metadata": event.metadata,
                "session_id": event.session_id,
                "device": event.user_agent
            })
        
        return journey
    
    @staticmethod
    def identify_power_users(
        db: Session,
        activity_threshold: int = 50,
        transaction_threshold: int = 5,
        time_period: timedelta = timedelta(days=30)
    ) -> List[Dict[str, Any]]:
        """
        Identify highly engaged power users.
        """
        cutoff_date = datetime.utcnow() - time_period
        
        # Query for active users with high engagement
        power_users = db.query(
            AnalyticsEvent.user_id,
            func.count(distinct(AnalyticsEvent.session_id)).label("sessions"),
            func.count(AnalyticsEvent.id).label("total_events"),
            func.count(
                case(
                    [(AnalyticsEvent.event_type == "prompt_purchased", 1)],
                    else_=None
                )
            ).label("purchases")
        ).filter(
            AnalyticsEvent.created_at >= cutoff_date
        ).group_by(
            AnalyticsEvent.user_id
        ).having(
            and_(
                func.count(AnalyticsEvent.id) >= activity_threshold,
                func.count(
                    case(
                        [(AnalyticsEvent.event_type == "prompt_purchased", 1)],
                        else_=None
                    )
                ) >= transaction_threshold
            )
        ).all()
        
        results = []
        for user in power_users:
            # Get user details
            user_obj = db.query(User).filter(User.id == user.user_id).first()
            if user_obj:
                results.append({
                    "user_id": str(user.user_id),
                    "email": user_obj.email,
                    "name": user_obj.name,
                    "sessions_count": user.sessions,
                    "total_events": user.total_events,
                    "purchases": user.purchases,
                    "engagement_score": user.total_events / user.sessions
                })
        
        return sorted(results, key=lambda x: x["engagement_score"], reverse=True)
    
    @staticmethod
    def predict_churn_risk(
        db: Session,
        user_id: str,
        baseline_days: int = 30
    ) -> Dict[str, Any]:
        """
        Predict user churn risk based on activity patterns.
        """
        # Get user's historical activity
        baseline_date = datetime.utcnow() - timedelta(days=baseline_days)
        recent_date = datetime.utcnow() - timedelta(days=7)
        
        # Baseline activity (first 23 days)
        baseline_events = db.query(func.count(AnalyticsEvent.id)).filter(
            and_(
                AnalyticsEvent.user_id == user_id,
                AnalyticsEvent.created_at >= baseline_date,
                AnalyticsEvent.created_at < recent_date
            )
        ).scalar()
        
        # Recent activity (last 7 days)
        recent_events = db.query(func.count(AnalyticsEvent.id)).filter(
            and_(
                AnalyticsEvent.user_id == user_id,
                AnalyticsEvent.created_at >= recent_date
            )
        ).scalar()
        
        # Calculate activity drop
        if baseline_events > 0:
            daily_baseline = baseline_events / 23
            daily_recent = recent_events / 7
            activity_change = ((daily_recent - daily_baseline) / daily_baseline) * 100
        else:
            activity_change = -100 if recent_events == 0 else 0
        
        # Determine churn risk
        if activity_change < -70:
            risk_level = "high"
            risk_score = 0.9
        elif activity_change < -40:
            risk_level = "medium"
            risk_score = 0.6
        elif activity_change < -10:
            risk_level = "low"
            risk_score = 0.3
        else:
            risk_level = "minimal"
            risk_score = 0.1
        
        # Get last activity
        last_event = db.query(AnalyticsEvent).filter(
            AnalyticsEvent.user_id == user_id
        ).order_by(
            AnalyticsEvent.created_at.desc()
        ).first()
        
        days_since_last_activity = (
            (datetime.utcnow() - last_event.created_at).days 
            if last_event else 999
        )
        
        return {
            "user_id": user_id,
            "churn_risk_level": risk_level,
            "churn_risk_score": risk_score,
            "activity_change_percent": round(activity_change, 2),
            "days_since_last_activity": days_since_last_activity,
            "baseline_events": baseline_events,
            "recent_events": recent_events,
            "recommendations": _get_retention_recommendations(risk_level)
        }


def _get_retention_recommendations(risk_level: str) -> List[str]:
    """
    Get retention strategy recommendations based on risk level.
    """
    recommendations = {
        "high": [
            "Send win-back email campaign",
            "Offer personalized discount",
            "Reach out with customer success call",
            "Highlight new features or prompts"
        ],
        "medium": [
            "Send engagement email with popular prompts",
            "Offer loyalty rewards",
            "Send tutorial or tips content"
        ],
        "low": [
            "Include in regular newsletter",
            "Show personalized recommendations"
        ],
        "minimal": [
            "Continue normal engagement"
        ]
    }
    
    return recommendations.get(risk_level, [])