from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, distinct
from typing import List, Optional, Dict
import logging

from api.database import get_db
from api.models.user import User
from api.models.prompt import Prompt
from api.middleware.auth import get_current_user
from api.services.analytics_service import AnalyticsService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/marketplace", tags=["marketplace"])

analytics_service = AnalyticsService()


@router.get("/categories")
async def get_categories(
    db: Session = Depends(get_db)
):
    """Get all available categories with prompt counts"""
    try:
        # Get categories with counts
        categories = db.query(
            Prompt.category,
            func.count(Prompt.id).label("count")
        ).filter(
            Prompt.is_active == True
        ).group_by(
            Prompt.category
        ).order_by(
            func.count(Prompt.id).desc()
        ).all()
        
        return {
            "categories": [
                {
                    "name": cat.category,
                    "count": cat.count
                } for cat in categories
            ]
        }
    except Exception as e:
        logger.error(f"Error fetching categories: {e}")
        return {"categories": []}


@router.get("/subcategories")
async def get_subcategories(
    category: str = Query(..., description="Parent category"),
    db: Session = Depends(get_db)
):
    """Get subcategories for a specific category"""
    try:
        subcategories = db.query(
            Prompt.subcategory,
            func.count(Prompt.id).label("count")
        ).filter(
            Prompt.category == category,
            Prompt.subcategory.isnot(None),
            Prompt.is_active == True
        ).group_by(
            Prompt.subcategory
        ).order_by(
            func.count(Prompt.id).desc()
        ).all()
        
        return {
            "category": category,
            "subcategories": [
                {
                    "name": sub.subcategory,
                    "count": sub.count
                } for sub in subcategories
            ]
        }
    except Exception as e:
        logger.error(f"Error fetching subcategories: {e}")
        return {"category": category, "subcategories": []}


@router.get("/trending")
async def get_trending_prompts(
    limit: int = Query(10, ge=1, le=50),
    timeframe: str = Query("week", pattern="^(day|week|month)$"),
    current_user: Optional[User] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get trending prompts based on recent sales and views"""
    try:
        # Calculate date threshold
        from datetime import datetime, timedelta
        
        if timeframe == "day":
            date_threshold = datetime.utcnow() - timedelta(days=1)
        elif timeframe == "week":
            date_threshold = datetime.utcnow() - timedelta(days=7)
        else:  # month
            date_threshold = datetime.utcnow() - timedelta(days=30)
        
        # Get trending prompts based on recent sales
        trending = db.query(Prompt).join(User).filter(
            Prompt.is_active == True,
            Prompt.updated_at >= date_threshold
        ).order_by(
            Prompt.total_sales.desc(),
            Prompt.rating_average.desc()
        ).limit(limit).all()
        
        # Track analytics
        if current_user:
            await analytics_service.track_event(
                user_id=current_user.id,
                event_type="trending_viewed",
                metadata={"timeframe": timeframe}
            )
        
        return {
            "timeframe": timeframe,
            "prompts": [
                {
                    "id": p.id,
                    "title": p.title,
                    "category": p.category,
                    "price": float(p.price),
                    "total_sales": p.total_sales,
                    "rating_average": p.rating_average,
                    "seller_name": p.seller.full_name or p.seller.email,
                    "seller_company": p.seller.company_name
                } for p in trending
            ]
        }
    except Exception as e:
        logger.error(f"Error fetching trending prompts: {e}")
        return {"timeframe": timeframe, "prompts": []}


@router.get("/featured")
async def get_featured_prompts(
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db)
):
    """Get featured/recommended prompts"""
    try:
        # Get high-rated prompts with good sales
        featured = db.query(Prompt).join(User).filter(
            Prompt.is_active == True,
            Prompt.rating_average >= 4.0,
            Prompt.total_sales >= 5
        ).order_by(
            (Prompt.rating_average * Prompt.total_sales).desc()
        ).limit(limit).all()
        
        return {
            "prompts": [
                {
                    "id": p.id,
                    "title": p.title,
                    "description": p.description[:200] + "..." if len(p.description) > 200 else p.description,
                    "category": p.category,
                    "price": float(p.price),
                    "total_sales": p.total_sales,
                    "rating_average": p.rating_average,
                    "seller_name": p.seller.full_name or p.seller.email,
                    "seller_company": p.seller.company_name
                } for p in featured
            ]
        }
    except Exception as e:
        logger.error(f"Error fetching featured prompts: {e}")
        return {"prompts": []}


@router.get("/statistics")
async def get_marketplace_statistics(
    db: Session = Depends(get_db)
):
    """Get overall marketplace statistics"""
    try:
        # Total prompts
        total_prompts = db.query(func.count(Prompt.id)).filter(
            Prompt.is_active == True
        ).scalar()
        
        # Total sellers
        total_sellers = db.query(func.count(distinct(Prompt.seller_id))).filter(
            Prompt.is_active == True
        ).scalar()
        
        # Total transactions
        from api.models.transaction import Transaction
        total_transactions = db.query(func.count(Transaction.id)).filter(
            Transaction.status == "completed"
        ).scalar()
        
        # Average price
        avg_price = db.query(func.avg(Prompt.price)).filter(
            Prompt.is_active == True
        ).scalar()
        
        # Top categories
        top_categories = db.query(
            Prompt.category,
            func.count(Prompt.id).label("count")
        ).filter(
            Prompt.is_active == True
        ).group_by(
            Prompt.category
        ).order_by(
            func.count(Prompt.id).desc()
        ).limit(5).all()
        
        return {
            "total_prompts": total_prompts or 0,
            "total_sellers": total_sellers or 0,
            "total_transactions": total_transactions or 0,
            "average_price": float(avg_price or 0),
            "top_categories": [
                {"name": cat.category, "count": cat.count}
                for cat in top_categories
            ]
        }
    except Exception as e:
        logger.error(f"Error fetching marketplace statistics: {e}")
        return {
            "total_prompts": 0,
            "total_sellers": 0,
            "total_transactions": 0,
            "average_price": 0,
            "top_categories": []
        }


@router.get("/sellers/{seller_id}")
async def get_seller_profile(
    seller_id: int,
    current_user: Optional[User] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get seller profile with their prompts"""
    try:
        # Get seller info
        seller = db.query(User).filter(User.id == seller_id).first()
        
        if not seller:
            return {"error": "Seller not found"}
        
        # Get seller's prompts
        prompts = db.query(Prompt).filter(
            Prompt.seller_id == seller_id,
            Prompt.is_active == True
        ).order_by(Prompt.created_at.desc()).all()
        
        # Calculate seller stats
        total_sales = sum(p.total_sales for p in prompts)
        avg_rating = None
        if prompts:
            rated_prompts = [p for p in prompts if p.rating_average is not None]
            if rated_prompts:
                avg_rating = sum(p.rating_average for p in rated_prompts) / len(rated_prompts)
        
        # Track view
        if current_user:
            await analytics_service.track_event(
                user_id=current_user.id,
                event_type="seller_profile_viewed",
                metadata={"seller_id": seller_id}
            )
        
        return {
            "seller": {
                "id": seller.id,
                "name": seller.full_name or seller.email,
                "company": seller.company_name,
                "member_since": seller.created_at.isoformat(),
                "total_prompts": len(prompts),
                "total_sales": total_sales,
                "average_rating": round(avg_rating, 2) if avg_rating else None
            },
            "prompts": [
                {
                    "id": p.id,
                    "title": p.title,
                    "category": p.category,
                    "price": float(p.price),
                    "total_sales": p.total_sales,
                    "rating_average": p.rating_average
                } for p in prompts[:20]  # Limit to 20 most recent
            ]
        }
    except Exception as e:
        logger.error(f"Error fetching seller profile: {e}")
        return {"error": "Failed to fetch seller profile"}