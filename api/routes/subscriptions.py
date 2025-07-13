"""
Subscription management endpoints for usage-based billing with floor pricing.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
import logging

from api.database import get_db
from api.models.user import User
from api.middleware.auth import get_current_user
from api.services.analytics_funnel import FunnelAnalytics
from integrations.stripe.client import StripeClient
from api.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()

stripe_client = StripeClient()


@router.post("/plans/create-products")
async def create_subscription_products(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create Stripe products and prices for subscription plans (admin only)"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        # Create products
        products = {}
        
        # Basic Plan Product
        basic_product_id = await stripe_client.create_product(
            name="AI Prompt Marketplace - Basic",
            description="Basic access to AI Prompt Marketplace with usage-based pricing",
            metadata={"plan": "basic", "marketplace": "ai-prompts"}
        )
        products["basic"] = basic_product_id
        
        # Professional Plan Product
        pro_product_id = await stripe_client.create_product(
            name="AI Prompt Marketplace - Professional",
            description="Professional access with higher limits and priority support",
            metadata={"plan": "professional", "marketplace": "ai-prompts"}
        )
        products["professional"] = pro_product_id
        
        # Enterprise Plan Product
        enterprise_product_id = await stripe_client.create_product(
            name="AI Prompt Marketplace - Enterprise",
            description="Enterprise access with custom limits and dedicated support",
            metadata={"plan": "enterprise", "marketplace": "ai-prompts"}
        )
        products["enterprise"] = enterprise_product_id
        
        # Create prices (base subscription + metered usage)
        prices = {}
        
        # Basic Plan: $29/month base + usage
        basic_base_price = stripe.Price.create(
            product=basic_product_id,
            currency="usd",
            unit_amount=2900,  # $29
            recurring={"interval": "month"}
        )
        
        basic_usage_price = await stripe_client.create_metered_price(
            product_id=basic_product_id,
            unit_amount=100,  # Base unit price (will be overridden by tiers)
            billing_scheme="tiered",
            tiers=[
                {"up_to": 100, "unit_amount": 0},      # First 100 included in base
                {"up_to": 500, "unit_amount": 50},     # $0.50 per prompt (101-500)
                {"up_to": "inf", "unit_amount": 30}    # $0.30 per prompt (501+)
            ]
        )
        
        prices["basic"] = {
            "base_price_id": basic_base_price.id,
            "usage_price_id": basic_usage_price
        }
        
        # Professional Plan: $99/month base + usage
        pro_base_price = stripe.Price.create(
            product=pro_product_id,
            currency="usd",
            unit_amount=9900,  # $99
            recurring={"interval": "month"}
        )
        
        pro_usage_price = await stripe_client.create_metered_price(
            product_id=pro_product_id,
            unit_amount=100,
            billing_scheme="tiered",
            tiers=[
                {"up_to": 500, "unit_amount": 0},      # First 500 included
                {"up_to": 2000, "unit_amount": 30},    # $0.30 per prompt (501-2000)
                {"up_to": "inf", "unit_amount": 20}    # $0.20 per prompt (2001+)
            ]
        )
        
        prices["professional"] = {
            "base_price_id": pro_base_price.id,
            "usage_price_id": pro_usage_price
        }
        
        # Enterprise Plan: $299/month base + usage
        enterprise_base_price = stripe.Price.create(
            product=enterprise_product_id,
            currency="usd",
            unit_amount=29900,  # $299
            recurring={"interval": "month"}
        )
        
        enterprise_usage_price = await stripe_client.create_metered_price(
            product_id=enterprise_product_id,
            unit_amount=100,
            billing_scheme="tiered",
            tiers=[
                {"up_to": 2000, "unit_amount": 0},     # First 2000 included
                {"up_to": 10000, "unit_amount": 20},   # $0.20 per prompt (2001-10000)
                {"up_to": "inf", "unit_amount": 10}    # $0.10 per prompt (10001+)
            ]
        )
        
        prices["enterprise"] = {
            "base_price_id": enterprise_base_price.id,
            "usage_price_id": enterprise_usage_price
        }
        
        return {
            "products": products,
            "prices": prices,
            "message": "Subscription products and prices created successfully"
        }
        
    except Exception as e:
        logger.error(f"Error creating subscription products: {e}")
        raise HTTPException(status_code=500, detail="Failed to create subscription products")


@router.get("/plans")
async def get_subscription_plans():
    """Get available subscription plans with pricing details"""
    plans = [
        {
            "id": "basic",
            "name": "Basic",
            "base_price": 29,
            "currency": "usd",
            "billing_interval": "month",
            "features": [
                "100 prompt uses included",
                "$0.50 per additional prompt (101-500)",
                "$0.30 per additional prompt (501+)",
                "Access to all marketplace prompts",
                "Basic analytics",
                "Email support"
            ],
            "usage_tiers": [
                {"range": "1-100", "price_per_unit": 0, "included": True},
                {"range": "101-500", "price_per_unit": 0.50},
                {"range": "501+", "price_per_unit": 0.30}
            ]
        },
        {
            "id": "professional",
            "name": "Professional",
            "base_price": 99,
            "currency": "usd",
            "billing_interval": "month",
            "features": [
                "500 prompt uses included",
                "$0.30 per additional prompt (501-2000)",
                "$0.20 per additional prompt (2001+)",
                "Priority access to new prompts",
                "Advanced analytics",
                "API access",
                "Priority email support"
            ],
            "usage_tiers": [
                {"range": "1-500", "price_per_unit": 0, "included": True},
                {"range": "501-2000", "price_per_unit": 0.30},
                {"range": "2001+", "price_per_unit": 0.20}
            ]
        },
        {
            "id": "enterprise",
            "name": "Enterprise",
            "base_price": 299,
            "currency": "usd",
            "billing_interval": "month",
            "features": [
                "2000 prompt uses included",
                "$0.20 per additional prompt (2001-10000)",
                "$0.10 per additional prompt (10001+)",
                "Custom prompt development",
                "Dedicated account manager",
                "Advanced API access",
                "Custom integrations",
                "24/7 phone support",
                "SLA guarantee"
            ],
            "usage_tiers": [
                {"range": "1-2000", "price_per_unit": 0, "included": True},
                {"range": "2001-10000", "price_per_unit": 0.20},
                {"range": "10001+", "price_per_unit": 0.10}
            ]
        }
    ]
    
    return {"plans": plans}


@router.post("/subscribe")
async def create_subscription(
    plan: str = Query(..., regex="^(basic|professional|enterprise)$"),
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new subscription for the current user"""
    session_id = request.headers.get("X-Session-ID", str(uuid.uuid4()))
    
    try:
        # Track funnel event
        FunnelAnalytics.track_funnel_event(
            db=db,
            user_id=str(current_user.id),
            event_type="plan_selected",
            funnel_name="subscription",
            session_id=session_id,
            metadata={"plan": plan}
        )
        
        # Get price IDs from config or database
        # In production, these would be stored in config or database
        price_mapping = {
            "basic": {
                "base_price_id": settings.stripe_basic_base_price_id,
                "usage_price_id": settings.stripe_basic_usage_price_id
            },
            "professional": {
                "base_price_id": settings.stripe_pro_base_price_id,
                "usage_price_id": settings.stripe_pro_usage_price_id
            },
            "enterprise": {
                "base_price_id": settings.stripe_enterprise_base_price_id,
                "usage_price_id": settings.stripe_enterprise_usage_price_id
            }
        }
        
        if plan not in price_mapping:
            raise HTTPException(status_code=400, detail="Invalid plan selected")
        
        prices = price_mapping[plan]
        
        # Create subscription with usage floor
        result = await stripe_client.create_subscription_with_usage_floor(
            customer_id=current_user.stripe_customer_id,
            base_price_id=prices["base_price_id"],
            usage_price_id=prices["usage_price_id"],
            base_items_metadata={"user_id": str(current_user.id), "plan": plan}
        )
        
        # Update user subscription info
        current_user.subscription_plan = plan
        current_user.subscription_id = result["subscription_id"]
        current_user.subscription_usage_item_id = result["usage_item_id"]
        current_user.subscription_status = result["status"]
        db.commit()
        
        # Track subscription started
        if result["status"] == "active":
            FunnelAnalytics.track_funnel_event(
                db=db,
                user_id=str(current_user.id),
                event_type="subscription_started",
                funnel_name="subscription",
                session_id=session_id,
                metadata={
                    "plan": plan,
                    "subscription_id": result["subscription_id"]
                }
            )
        
        return {
            "subscription_id": result["subscription_id"],
            "plan": plan,
            "status": result["status"],
            "client_secret": result["client_secret"],
            "message": "Subscription created successfully"
        }
        
    except Exception as e:
        logger.error(f"Error creating subscription: {e}")
        raise HTTPException(status_code=500, detail="Failed to create subscription")


@router.get("/current")
async def get_current_subscription(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get current user's subscription details including usage"""
    if not current_user.subscription_id:
        return {
            "has_subscription": False,
            "message": "No active subscription"
        }
    
    try:
        # Get subscription from Stripe
        subscription = stripe.Subscription.retrieve(
            current_user.subscription_id,
            expand=["items.data.price"]
        )
        
        # Get current usage if available
        usage_summary = None
        if current_user.subscription_usage_item_id:
            usage_summary = await stripe_client.get_usage_summary(
                current_user.subscription_usage_item_id
            )
        
        # Calculate billing period dates
        current_period_start = datetime.fromtimestamp(subscription.current_period_start)
        current_period_end = datetime.fromtimestamp(subscription.current_period_end)
        
        return {
            "has_subscription": True,
            "subscription_id": subscription.id,
            "plan": current_user.subscription_plan,
            "status": subscription.status,
            "current_period_start": current_period_start.isoformat(),
            "current_period_end": current_period_end.isoformat(),
            "cancel_at_period_end": subscription.cancel_at_period_end,
            "usage": {
                "current_usage": usage_summary["total_usage"] if usage_summary else 0,
                "included_usage": _get_included_usage(current_user.subscription_plan),
                "overage_rate": _get_overage_rate(current_user.subscription_plan, usage_summary["total_usage"] if usage_summary else 0)
            }
        }
        
    except Exception as e:
        logger.error(f"Error fetching subscription: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch subscription details")


@router.post("/cancel")
async def cancel_subscription(
    immediate: bool = Query(False, description="Cancel immediately vs at period end"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Cancel current subscription"""
    if not current_user.subscription_id:
        raise HTTPException(status_code=400, detail="No active subscription to cancel")
    
    try:
        if immediate:
            # Cancel immediately
            result = await stripe_client.cancel_subscription(current_user.subscription_id)
        else:
            # Cancel at period end
            subscription = stripe.Subscription.modify(
                current_user.subscription_id,
                cancel_at_period_end=True
            )
            result = {
                "subscription_id": subscription.id,
                "status": subscription.status,
                "cancel_at_period_end": subscription.cancel_at_period_end,
                "current_period_end": subscription.current_period_end
            }
        
        # Update user record
        if immediate:
            current_user.subscription_status = "cancelled"
            current_user.subscription_id = None
            current_user.subscription_usage_item_id = None
        
        db.commit()
        
        # Track cancellation
        await analytics_service.track_event(
            user_id=current_user.id,
            event_type="subscription_cancelled",
            metadata={
                "plan": current_user.subscription_plan,
                "immediate": immediate
            }
        )
        
        return {
            "message": "Subscription cancelled successfully",
            "immediate": immediate,
            **result
        }
        
    except Exception as e:
        logger.error(f"Error cancelling subscription: {e}")
        raise HTTPException(status_code=500, detail="Failed to cancel subscription")


@router.post("/track-usage")
async def track_prompt_usage(
    prompt_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Track usage for metered billing when a prompt is used"""
    if not current_user.subscription_usage_item_id:
        # User doesn't have metered billing, use pay-per-use instead
        return {"tracked": False, "reason": "No usage-based subscription"}
    
    try:
        # Create usage record in Stripe
        usage_record = await stripe_client.create_usage_record(
            subscription_item_id=current_user.subscription_usage_item_id,
            quantity=1,  # 1 prompt use
            metadata={
                "user_id": str(current_user.id),
                "prompt_id": str(prompt_id)
            }
        )
        
        # Track in analytics
        await analytics_service.track_event(
            user_id=current_user.id,
            event_type="prompt_used",
            prompt_id=prompt_id,
            metadata={
                "subscription_plan": current_user.subscription_plan,
                "usage_record_id": usage_record["id"]
            }
        )
        
        return {
            "tracked": True,
            "usage_record_id": usage_record["id"],
            "message": "Usage tracked successfully"
        }
        
    except Exception as e:
        logger.error(f"Error tracking usage: {e}")
        # Don't fail the request if usage tracking fails
        return {"tracked": False, "error": str(e)}


def _get_included_usage(plan: str) -> int:
    """Get included usage for a plan"""
    included_usage = {
        "basic": 100,
        "professional": 500,
        "enterprise": 2000
    }
    return included_usage.get(plan, 0)


def _get_overage_rate(plan: str, current_usage: int) -> float:
    """Get current overage rate based on usage tier"""
    if plan == "basic":
        if current_usage <= 100:
            return 0
        elif current_usage <= 500:
            return 0.50
        else:
            return 0.30
    elif plan == "professional":
        if current_usage <= 500:
            return 0
        elif current_usage <= 2000:
            return 0.30
        else:
            return 0.20
    elif plan == "enterprise":
        if current_usage <= 2000:
            return 0
        elif current_usage <= 10000:
            return 0.20
        else:
            return 0.10
    return 0


# Import required modules
from api.services.analytics_service import AnalyticsService
import uuid
from fastapi import Request
import stripe

analytics_service = AnalyticsService()