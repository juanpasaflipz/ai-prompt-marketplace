"""
Analytics API endpoints for viewing funnel metrics and user behavior.
"""

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import logging

from api.database import get_db
from api.models.user import User
from api.middleware.auth import get_current_user, require_role
from api.services.analytics_funnel import FunnelAnalytics, UserBehaviorAnalytics
from api.services.analytics_service import AnalyticsService

logger = logging.getLogger(__name__)
router = APIRouter()

analytics_service = AnalyticsService()


@router.get("/funnel/purchase")
async def get_purchase_funnel_analytics(
    start_date: datetime = Query(..., description="Start date for analysis"),
    end_date: datetime = Query(..., description="End date for analysis"),
    current_user: User = Depends(require_role(["admin", "seller"])),
    db: Session = Depends(get_db)
):
    """Get purchase funnel conversion rates"""
    try:
        # For sellers, filter by their prompts only
        user_segment = None
        if current_user.role == "seller":
            # This would need to be enhanced to filter by seller's prompts
            user_segment = {"seller_id": current_user.id}
        
        funnel_data = FunnelAnalytics.calculate_funnel_conversion(
            db=db,
            funnel_steps=FunnelAnalytics.PURCHASE_FUNNEL,
            start_date=start_date,
            end_date=end_date,
            user_segment=user_segment
        )
        
        return funnel_data
    
    except Exception as e:
        logger.error(f"Error calculating purchase funnel: {e}")
        raise HTTPException(status_code=500, detail="Failed to calculate funnel metrics")


@router.get("/funnel/seller-onboarding")
async def get_seller_onboarding_funnel(
    start_date: datetime = Query(..., description="Start date for analysis"),
    end_date: datetime = Query(..., description="End date for analysis"),
    current_user: User = Depends(require_role(["admin"])),
    db: Session = Depends(get_db)
):
    """Get seller onboarding funnel conversion rates"""
    try:
        funnel_data = FunnelAnalytics.calculate_funnel_conversion(
            db=db,
            funnel_steps=FunnelAnalytics.SELLER_FUNNEL,
            start_date=start_date,
            end_date=end_date
        )
        
        return funnel_data
    
    except Exception as e:
        logger.error(f"Error calculating seller funnel: {e}")
        raise HTTPException(status_code=500, detail="Failed to calculate funnel metrics")


@router.get("/funnel/subscription")
async def get_subscription_funnel(
    start_date: datetime = Query(..., description="Start date for analysis"),
    end_date: datetime = Query(..., description="End date for analysis"),
    current_user: User = Depends(require_role(["admin"])),
    db: Session = Depends(get_db)
):
    """Get subscription conversion funnel"""
    try:
        funnel_data = FunnelAnalytics.calculate_funnel_conversion(
            db=db,
            funnel_steps=FunnelAnalytics.SUBSCRIPTION_FUNNEL,
            start_date=start_date,
            end_date=end_date
        )
        
        return funnel_data
    
    except Exception as e:
        logger.error(f"Error calculating subscription funnel: {e}")
        raise HTTPException(status_code=500, detail="Failed to calculate funnel metrics")


@router.get("/abandoned-carts")
async def get_abandoned_carts(
    hours_threshold: int = Query(1, ge=1, le=24, description="Hours before cart is considered abandoned"),
    current_user: User = Depends(require_role(["admin"])),
    db: Session = Depends(get_db)
):
    """Get list of abandoned shopping carts"""
    try:
        abandoned_carts = FunnelAnalytics.get_abandoned_carts(
            db=db,
            time_threshold=timedelta(hours=hours_threshold)
        )
        
        return {
            "threshold_hours": hours_threshold,
            "total_abandoned": len(abandoned_carts),
            "total_value": sum(cart["cart_value"] for cart in abandoned_carts),
            "carts": abandoned_carts
        }
    
    except Exception as e:
        logger.error(f"Error fetching abandoned carts: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch abandoned carts")


@router.get("/cohort-retention")
async def get_cohort_retention(
    cohort_date: datetime = Query(..., description="Date of cohort to analyze"),
    current_user: User = Depends(require_role(["admin"])),
    db: Session = Depends(get_db)
):
    """Get retention metrics for a user cohort"""
    try:
        retention_data = FunnelAnalytics.calculate_cohort_retention(
            db=db,
            cohort_date=cohort_date
        )
        
        return retention_data
    
    except Exception as e:
        logger.error(f"Error calculating cohort retention: {e}")
        raise HTTPException(status_code=500, detail="Failed to calculate retention metrics")


@router.get("/user/{user_id}/lifetime-value")
async def get_user_lifetime_value(
    user_id: str,
    include_projections: bool = Query(True, description="Include LTV projections"),
    current_user: User = Depends(require_role(["admin"])),
    db: Session = Depends(get_db)
):
    """Calculate user lifetime value"""
    try:
        ltv_data = FunnelAnalytics.calculate_user_lifetime_value(
            db=db,
            user_id=user_id,
            include_projections=include_projections
        )
        
        return ltv_data
    
    except Exception as e:
        logger.error(f"Error calculating user LTV: {e}")
        raise HTTPException(status_code=500, detail="Failed to calculate lifetime value")


@router.get("/user/{user_id}/journey")
async def get_user_journey(
    user_id: str,
    limit: int = Query(100, ge=10, le=500),
    current_user: User = Depends(require_role(["admin"])),
    db: Session = Depends(get_db)
):
    """Get complete user journey with all touchpoints"""
    try:
        journey = UserBehaviorAnalytics.track_user_journey(
            db=db,
            user_id=user_id,
            limit=limit
        )
        
        return {
            "user_id": user_id,
            "total_events": len(journey),
            "journey": journey
        }
    
    except Exception as e:
        logger.error(f"Error fetching user journey: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch user journey")


@router.get("/power-users")
async def get_power_users(
    days: int = Query(30, ge=7, le=90, description="Time period to analyze"),
    activity_threshold: int = Query(50, ge=10, le=500),
    transaction_threshold: int = Query(5, ge=1, le=50),
    current_user: User = Depends(require_role(["admin"])),
    db: Session = Depends(get_db)
):
    """Identify highly engaged power users"""
    try:
        power_users = UserBehaviorAnalytics.identify_power_users(
            db=db,
            activity_threshold=activity_threshold,
            transaction_threshold=transaction_threshold,
            time_period=timedelta(days=days)
        )
        
        return {
            "period_days": days,
            "criteria": {
                "min_events": activity_threshold,
                "min_transactions": transaction_threshold
            },
            "total_power_users": len(power_users),
            "users": power_users
        }
    
    except Exception as e:
        logger.error(f"Error identifying power users: {e}")
        raise HTTPException(status_code=500, detail="Failed to identify power users")


@router.get("/user/{user_id}/churn-risk")
async def get_user_churn_risk(
    user_id: str,
    baseline_days: int = Query(30, ge=14, le=90),
    current_user: User = Depends(require_role(["admin"])),
    db: Session = Depends(get_db)
):
    """Predict user churn risk"""
    try:
        churn_risk = UserBehaviorAnalytics.predict_churn_risk(
            db=db,
            user_id=user_id,
            baseline_days=baseline_days
        )
        
        return churn_risk
    
    except Exception as e:
        logger.error(f"Error predicting churn risk: {e}")
        raise HTTPException(status_code=500, detail="Failed to predict churn risk")


@router.get("/events/recent")
async def get_recent_events(
    event_type: Optional[str] = Query(None, description="Filter by event type"),
    limit: int = Query(100, ge=10, le=1000),
    current_user: User = Depends(require_role(["admin"])),
    db: Session = Depends(get_db)
):
    """Get recent analytics events"""
    try:
        from api.models.analytics import AnalyticsEvent
        
        query = db.query(AnalyticsEvent)
        
        if event_type:
            query = query.filter(AnalyticsEvent.event_type == event_type)
        
        events = query.order_by(
            AnalyticsEvent.created_at.desc()
        ).limit(limit).all()
        
        return {
            "total": len(events),
            "events": [
                {
                    "id": str(event.id),
                    "user_id": str(event.user_id),
                    "event_type": event.event_type,
                    "event_category": event.event_category,
                    "metadata": event.metadata,
                    "created_at": event.created_at.isoformat()
                }
                for event in events
            ]
        }
    
    except Exception as e:
        logger.error(f"Error fetching recent events: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch events")


@router.post("/events/custom")
async def track_custom_event(
    event_type: str,
    metadata: Optional[Dict[str, Any]] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Track a custom analytics event"""
    try:
        await analytics_service.track_event(
            user_id=current_user.id,
            event_type=event_type,
            metadata=metadata or {}
        )
        
        return {"status": "tracked", "event_type": event_type}
    
    except Exception as e:
        logger.error(f"Error tracking custom event: {e}")
        raise HTTPException(status_code=500, detail="Failed to track event")