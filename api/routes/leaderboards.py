"""
Leaderboards and gamification endpoints.
"""

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, case, desc
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import logging

from api.database import get_db
from api.models.user import User
from api.models.prompt import Prompt
from api.models.transaction import Transaction
from api.models.rating import PromptRating
from api.models.share import PromptShare
from api.middleware.auth import get_current_user
from api.services.cache_service import get_cache_service
from api.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()

# Initialize cache
cache = get_cache_service(
    host=settings.redis_host,
    port=settings.redis_port,
    password=settings.redis_password,
    db=settings.redis_db
)


@router.get("/sellers/top")
async def get_top_sellers(
    period: str = Query("all_time", regex="^(week|month|all_time)$"),
    category: Optional[str] = None,
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db)
):
    """Get top sellers by revenue or sales volume"""
    # Check cache first
    cache_key = f"leaderboard:sellers:{period}:{category or 'all'}:{limit}"
    cached_result = cache.get(cache_key)
    if cached_result:
        return cached_result
    
    # Build query
    query = db.query(
        User.id,
        User.email,
        User.full_name,
        User.company_name,
        func.count(distinct(Transaction.id)).label("total_sales"),
        func.sum(Transaction.amount).label("total_revenue"),
        func.avg(PromptRating.rating).label("avg_rating"),
        func.count(distinct(Prompt.id)).label("prompt_count")
    ).join(
        Prompt, Prompt.seller_id == User.id
    ).join(
        Transaction, Transaction.prompt_id == Prompt.id
    ).outerjoin(
        PromptRating, PromptRating.prompt_id == Prompt.id
    ).filter(
        Transaction.status == "completed"
    )
    
    # Apply time filter
    if period == "week":
        start_date = datetime.utcnow() - timedelta(days=7)
        query = query.filter(Transaction.created_at >= start_date)
    elif period == "month":
        start_date = datetime.utcnow() - timedelta(days=30)
        query = query.filter(Transaction.created_at >= start_date)
    
    # Apply category filter
    if category:
        query = query.filter(Prompt.category == category)
    
    # Group and order
    query = query.group_by(
        User.id, User.email, User.full_name, User.company_name
    ).order_by(
        desc("total_revenue")
    ).limit(limit)
    
    sellers = query.all()
    
    # Format response with badges
    leaderboard = []
    for idx, seller in enumerate(sellers):
        badges = _calculate_seller_badges(
            total_sales=seller.total_sales,
            total_revenue=float(seller.total_revenue) if seller.total_revenue else 0,
            avg_rating=float(seller.avg_rating) if seller.avg_rating else 0,
            prompt_count=seller.prompt_count,
            rank=idx + 1
        )
        
        leaderboard.append({
            "rank": idx + 1,
            "seller": {
                "id": str(seller.id),
                "name": seller.full_name or seller.email,
                "company": seller.company_name
            },
            "stats": {
                "total_sales": seller.total_sales,
                "total_revenue": float(seller.total_revenue) if seller.total_revenue else 0,
                "average_rating": round(float(seller.avg_rating), 2) if seller.avg_rating else None,
                "prompt_count": seller.prompt_count
            },
            "badges": badges
        })
    
    result = {
        "period": period,
        "category": category,
        "leaderboard": leaderboard
    }
    
    # Cache for 1 hour
    cache.set(cache_key, result, ttl=3600)
    
    return result


@router.get("/prompts/top")
async def get_top_prompts(
    period: str = Query("all_time", regex="^(week|month|all_time)$"),
    category: Optional[str] = None,
    sort_by: str = Query("revenue", regex="^(revenue|sales|rating)$"),
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db)
):
    """Get top performing prompts"""
    # Build base query
    query = db.query(
        Prompt.id,
        Prompt.title,
        Prompt.category,
        Prompt.price,
        Prompt.total_sales,
        Prompt.rating_average,
        Prompt.rating_count,
        User.full_name.label("seller_name"),
        User.company_name.label("seller_company"),
        func.sum(Transaction.amount).label("total_revenue")
    ).join(
        User, Prompt.seller_id == User.id
    ).outerjoin(
        Transaction, and_(
            Transaction.prompt_id == Prompt.id,
            Transaction.status == "completed"
        )
    ).filter(
        Prompt.is_active == True
    )
    
    # Apply time filter
    if period == "week":
        start_date = datetime.utcnow() - timedelta(days=7)
        query = query.filter(Transaction.created_at >= start_date)
    elif period == "month":
        start_date = datetime.utcnow() - timedelta(days=30)
        query = query.filter(Transaction.created_at >= start_date)
    
    # Apply category filter
    if category:
        query = query.filter(Prompt.category == category)
    
    # Group by prompt
    query = query.group_by(
        Prompt.id,
        Prompt.title,
        Prompt.category,
        Prompt.price,
        Prompt.total_sales,
        Prompt.rating_average,
        Prompt.rating_count,
        User.full_name,
        User.company_name
    )
    
    # Apply sorting
    if sort_by == "revenue":
        query = query.order_by(desc("total_revenue"))
    elif sort_by == "sales":
        query = query.order_by(desc(Prompt.total_sales))
    elif sort_by == "rating":
        query = query.order_by(desc(Prompt.rating_average))
    
    prompts = query.limit(limit).all()
    
    # Format response
    leaderboard = []
    for idx, prompt in enumerate(prompts):
        leaderboard.append({
            "rank": idx + 1,
            "prompt": {
                "id": str(prompt.id),
                "title": prompt.title,
                "category": prompt.category,
                "price": float(prompt.price)
            },
            "seller": {
                "name": prompt.seller_name or "Anonymous",
                "company": prompt.seller_company
            },
            "stats": {
                "total_sales": prompt.total_sales,
                "total_revenue": float(prompt.total_revenue) if prompt.total_revenue else 0,
                "rating_average": float(prompt.rating_average) if prompt.rating_average else None,
                "rating_count": prompt.rating_count
            }
        })
    
    return {
        "period": period,
        "category": category,
        "sort_by": sort_by,
        "leaderboard": leaderboard
    }


@router.get("/users/{user_id}/achievements")
async def get_user_achievements(
    user_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get achievements and badges for a user"""
    # Check permissions
    if str(current_user.id) != user_id and current_user.role != "admin":
        # Allow viewing public achievements
        pass
    
    # Get user
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Calculate seller stats
    seller_stats = db.query(
        func.count(distinct(Transaction.id)).label("total_sales"),
        func.sum(Transaction.amount).label("total_revenue"),
        func.count(distinct(Prompt.id)).label("prompt_count"),
        func.avg(PromptRating.rating).label("avg_rating")
    ).join(
        Prompt, Prompt.seller_id == user_id
    ).outerjoin(
        Transaction, and_(
            Transaction.prompt_id == Prompt.id,
            Transaction.status == "completed"
        )
    ).outerjoin(
        PromptRating, PromptRating.prompt_id == Prompt.id
    ).first()
    
    # Calculate buyer stats
    buyer_stats = db.query(
        func.count(distinct(Transaction.id)).label("purchases_made"),
        func.sum(Transaction.amount).label("total_spent"),
        func.count(distinct(PromptRating.id)).label("reviews_written"),
        func.count(distinct(PromptShare.id)).label("prompts_shared")
    ).outerjoin(
        Transaction, and_(
            Transaction.buyer_id == user_id,
            Transaction.status == "completed"
        )
    ).outerjoin(
        PromptRating, PromptRating.user_id == user_id
    ).outerjoin(
        PromptShare, PromptShare.user_id == user_id
    ).first()
    
    # Calculate badges
    seller_badges = _calculate_seller_badges(
        total_sales=seller_stats.total_sales or 0,
        total_revenue=float(seller_stats.total_revenue or 0),
        avg_rating=float(seller_stats.avg_rating or 0),
        prompt_count=seller_stats.prompt_count or 0,
        rank=None  # Calculate separately if needed
    )
    
    buyer_badges = _calculate_buyer_badges(
        purchases_made=buyer_stats.purchases_made or 0,
        reviews_written=buyer_stats.reviews_written or 0,
        prompts_shared=buyer_stats.prompts_shared or 0
    )
    
    # Combine achievements
    achievements = {
        "user": {
            "id": str(user.id),
            "name": user.full_name or user.email,
            "company": user.company_name,
            "member_since": user.created_at.isoformat()
        },
        "seller_stats": {
            "total_sales": seller_stats.total_sales or 0,
            "total_revenue": float(seller_stats.total_revenue or 0),
            "prompt_count": seller_stats.prompt_count or 0,
            "average_rating": round(float(seller_stats.avg_rating), 2) if seller_stats.avg_rating else None
        },
        "buyer_stats": {
            "purchases_made": buyer_stats.purchases_made or 0,
            "total_spent": float(buyer_stats.total_spent or 0),
            "reviews_written": buyer_stats.reviews_written or 0,
            "prompts_shared": buyer_stats.prompts_shared or 0
        },
        "badges": {
            "seller": seller_badges,
            "buyer": buyer_badges
        }
    }
    
    return achievements


@router.get("/categories/trending")
async def get_trending_categories(
    period: str = Query("week", regex="^(day|week|month)$"),
    db: Session = Depends(get_db)
):
    """Get trending categories based on recent activity"""
    # Calculate date threshold
    if period == "day":
        start_date = datetime.utcnow() - timedelta(days=1)
    elif period == "week":
        start_date = datetime.utcnow() - timedelta(days=7)
    else:  # month
        start_date = datetime.utcnow() - timedelta(days=30)
    
    # Get category trends
    trends = db.query(
        Prompt.category,
        func.count(distinct(Transaction.id)).label("transaction_count"),
        func.sum(Transaction.amount).label("revenue"),
        func.count(distinct(Transaction.buyer_id)).label("unique_buyers"),
        func.avg(PromptRating.rating).label("avg_rating")
    ).join(
        Transaction, and_(
            Transaction.prompt_id == Prompt.id,
            Transaction.status == "completed",
            Transaction.created_at >= start_date
        )
    ).outerjoin(
        PromptRating, PromptRating.prompt_id == Prompt.id
    ).group_by(
        Prompt.category
    ).order_by(
        desc("transaction_count")
    ).all()
    
    # Calculate growth rates (would need historical data)
    trending = []
    for trend in trends:
        trending.append({
            "category": trend.category,
            "stats": {
                "transactions": trend.transaction_count,
                "revenue": float(trend.revenue) if trend.revenue else 0,
                "unique_buyers": trend.unique_buyers,
                "average_rating": round(float(trend.avg_rating), 2) if trend.avg_rating else None
            },
            "trend": "rising"  # Placeholder - would calculate from historical data
        })
    
    return {
        "period": period,
        "trending_categories": trending
    }


def _calculate_seller_badges(
    total_sales: int,
    total_revenue: float,
    avg_rating: float,
    prompt_count: int,
    rank: Optional[int]
) -> List[Dict[str, Any]]:
    """Calculate badges for sellers based on achievements"""
    badges = []
    
    # Sales milestones
    if total_sales >= 1000:
        badges.append({
            "id": "platinum_seller",
            "name": "Platinum Seller",
            "description": "1000+ sales",
            "icon": "trophy",
            "tier": "platinum"
        })
    elif total_sales >= 500:
        badges.append({
            "id": "gold_seller",
            "name": "Gold Seller",
            "description": "500+ sales",
            "icon": "medal",
            "tier": "gold"
        })
    elif total_sales >= 100:
        badges.append({
            "id": "silver_seller",
            "name": "Silver Seller",
            "description": "100+ sales",
            "icon": "award",
            "tier": "silver"
        })
    elif total_sales >= 10:
        badges.append({
            "id": "bronze_seller",
            "name": "Bronze Seller",
            "description": "10+ sales",
            "icon": "certificate",
            "tier": "bronze"
        })
    
    # Revenue milestones
    if total_revenue >= 50000:
        badges.append({
            "id": "revenue_champion",
            "name": "Revenue Champion",
            "description": "$50k+ in sales",
            "icon": "dollar-sign",
            "tier": "platinum"
        })
    elif total_revenue >= 10000:
        badges.append({
            "id": "high_earner",
            "name": "High Earner",
            "description": "$10k+ in sales",
            "icon": "coins",
            "tier": "gold"
        })
    
    # Rating achievements
    if avg_rating >= 4.8 and total_sales >= 20:
        badges.append({
            "id": "top_rated",
            "name": "Top Rated Seller",
            "description": "4.8+ rating with 20+ sales",
            "icon": "star",
            "tier": "gold"
        })
    
    # Prompt variety
    if prompt_count >= 50:
        badges.append({
            "id": "prolific_creator",
            "name": "Prolific Creator",
            "description": "50+ prompts created",
            "icon": "pen",
            "tier": "gold"
        })
    elif prompt_count >= 20:
        badges.append({
            "id": "active_creator",
            "name": "Active Creator",
            "description": "20+ prompts created",
            "icon": "edit",
            "tier": "silver"
        })
    
    # Leaderboard position
    if rank == 1:
        badges.append({
            "id": "number_one",
            "name": "#1 Seller",
            "description": "Top seller on leaderboard",
            "icon": "crown",
            "tier": "platinum"
        })
    elif rank and rank <= 3:
        badges.append({
            "id": "top_three",
            "name": f"Top {rank} Seller",
            "description": f"#{rank} on leaderboard",
            "icon": "podium",
            "tier": "gold"
        })
    elif rank and rank <= 10:
        badges.append({
            "id": "top_ten",
            "name": "Top 10 Seller",
            "description": "Top 10 on leaderboard",
            "icon": "chart-line",
            "tier": "silver"
        })
    
    return badges


def _calculate_buyer_badges(
    purchases_made: int,
    reviews_written: int,
    prompts_shared: int
) -> List[Dict[str, Any]]:
    """Calculate badges for buyers based on activity"""
    badges = []
    
    # Purchase milestones
    if purchases_made >= 100:
        badges.append({
            "id": "power_user",
            "name": "Power User",
            "description": "100+ purchases",
            "icon": "zap",
            "tier": "platinum"
        })
    elif purchases_made >= 50:
        badges.append({
            "id": "frequent_buyer",
            "name": "Frequent Buyer",
            "description": "50+ purchases",
            "icon": "shopping-bag",
            "tier": "gold"
        })
    elif purchases_made >= 10:
        badges.append({
            "id": "regular_customer",
            "name": "Regular Customer",
            "description": "10+ purchases",
            "icon": "user-check",
            "tier": "silver"
        })
    
    # Review contributions
    if reviews_written >= 50:
        badges.append({
            "id": "review_master",
            "name": "Review Master",
            "description": "50+ reviews written",
            "icon": "message-square",
            "tier": "gold"
        })
    elif reviews_written >= 20:
        badges.append({
            "id": "helpful_reviewer",
            "name": "Helpful Reviewer",
            "description": "20+ reviews written",
            "icon": "thumbs-up",
            "tier": "silver"
        })
    
    # Social sharing
    if prompts_shared >= 50:
        badges.append({
            "id": "social_champion",
            "name": "Social Champion",
            "description": "50+ prompts shared",
            "icon": "share-2",
            "tier": "gold"
        })
    elif prompts_shared >= 10:
        badges.append({
            "id": "community_supporter",
            "name": "Community Supporter",
            "description": "10+ prompts shared",
            "icon": "users",
            "tier": "silver"
        })
    
    return badges


# Import needed
from sqlalchemy import distinct