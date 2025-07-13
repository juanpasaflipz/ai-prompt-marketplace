"""
Rating and review endpoints for prompts.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from typing import Optional, List
from datetime import datetime
import logging

from api.database import get_db
from api.models.user import User
from api.models.prompt import Prompt
from api.models.transaction import Transaction
from api.models.rating import PromptRating, RatingHelpfulness
from api.middleware.auth import get_current_user
from api.services.analytics_service import AnalyticsService
from api.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()

analytics_service = AnalyticsService()


@router.post("/prompts/{prompt_id}/rate")
async def rate_prompt(
    prompt_id: str,
    rating: int = Query(..., ge=1, le=5),
    review_title: Optional[str] = Query(None, max_length=200),
    review_text: Optional[str] = Query(None, max_length=5000),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Rate and review a prompt"""
    # Check if prompt exists
    prompt = db.query(Prompt).filter(Prompt.id == prompt_id).first()
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")
    
    # Check if user has purchased the prompt
    transaction = db.query(Transaction).filter(
        Transaction.buyer_id == current_user.id,
        Transaction.prompt_id == prompt_id,
        Transaction.status == "completed"
    ).first()
    
    is_verified_purchase = transaction is not None
    
    # Check if user already rated this prompt
    existing_rating = db.query(PromptRating).filter(
        PromptRating.prompt_id == prompt_id,
        PromptRating.user_id == current_user.id
    ).first()
    
    if existing_rating:
        # Update existing rating
        existing_rating.rating = rating
        existing_rating.review_title = review_title
        existing_rating.review_text = review_text
        existing_rating.updated_at = datetime.utcnow()
        
        db.commit()
        db.refresh(existing_rating)
        
        # Track update event
        await analytics_service.track_event(
            user_id=current_user.id,
            event_type="prompt_rating_updated",
            prompt_id=prompt_id,
            metadata={
                "rating": rating,
                "previous_rating": existing_rating.rating,
                "has_review": bool(review_text)
            }
        )
        
        rating_obj = existing_rating
    else:
        # Create new rating
        rating_obj = PromptRating(
            prompt_id=prompt_id,
            user_id=current_user.id,
            transaction_id=transaction.id if transaction else None,
            rating=rating,
            review_title=review_title,
            review_text=review_text,
            is_verified_purchase=is_verified_purchase
        )
        
        db.add(rating_obj)
        db.commit()
        db.refresh(rating_obj)
        
        # Track creation event
        await analytics_service.track_event(
            user_id=current_user.id,
            event_type="prompt_rated",
            prompt_id=prompt_id,
            metadata={
                "rating": rating,
                "has_review": bool(review_text),
                "is_verified_purchase": is_verified_purchase
            }
        )
    
    # Update prompt's average rating
    _update_prompt_rating_stats(db, prompt_id)
    
    return {
        "rating_id": str(rating_obj.id),
        "prompt_id": prompt_id,
        "rating": rating_obj.rating,
        "review_title": rating_obj.review_title,
        "review_text": rating_obj.review_text,
        "is_verified_purchase": rating_obj.is_verified_purchase,
        "created_at": rating_obj.created_at.isoformat(),
        "updated_at": rating_obj.updated_at.isoformat()
    }


@router.get("/prompts/{prompt_id}/ratings")
async def get_prompt_ratings(
    prompt_id: str,
    sort_by: str = Query("helpful", regex="^(helpful|recent|rating)$"),
    filter_rating: Optional[int] = Query(None, ge=1, le=5),
    verified_only: bool = Query(False),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    """Get ratings and reviews for a prompt"""
    # Build query
    query = db.query(PromptRating).join(User).filter(PromptRating.prompt_id == prompt_id)
    
    # Apply filters
    if filter_rating:
        query = query.filter(PromptRating.rating == filter_rating)
    
    if verified_only:
        query = query.filter(PromptRating.is_verified_purchase == True)
    
    # Apply sorting
    if sort_by == "helpful":
        query = query.order_by(PromptRating.helpful_count.desc())
    elif sort_by == "recent":
        query = query.order_by(PromptRating.created_at.desc())
    elif sort_by == "rating":
        query = query.order_by(PromptRating.rating.desc())
    
    # Get total count
    total = query.count()
    
    # Get paginated results
    ratings = query.offset(offset).limit(limit).all()
    
    # Format response
    rating_list = []
    for rating in ratings:
        user = rating.user
        rating_list.append({
            "rating_id": str(rating.id),
            "rating": rating.rating,
            "review_title": rating.review_title,
            "review_text": rating.review_text,
            "is_verified_purchase": rating.is_verified_purchase,
            "helpful_count": rating.helpful_count,
            "not_helpful_count": rating.not_helpful_count,
            "created_at": rating.created_at.isoformat(),
            "user": {
                "id": str(user.id),
                "name": user.full_name or "Anonymous",
                "company": user.company_name
            }
        })
    
    # Get rating distribution
    distribution = db.query(
        PromptRating.rating,
        func.count(PromptRating.id).label("count")
    ).filter(
        PromptRating.prompt_id == prompt_id
    ).group_by(
        PromptRating.rating
    ).all()
    
    rating_distribution = {i: 0 for i in range(1, 6)}
    for dist in distribution:
        rating_distribution[dist.rating] = dist.count
    
    return {
        "ratings": rating_list,
        "total": total,
        "rating_distribution": rating_distribution,
        "pagination": {
            "limit": limit,
            "offset": offset,
            "pages": (total + limit - 1) // limit
        }
    }


@router.post("/ratings/{rating_id}/helpful")
async def mark_rating_helpful(
    rating_id: str,
    is_helpful: bool = Query(..., description="True if helpful, False if not helpful"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Mark a rating as helpful or not helpful"""
    # Get the rating
    rating = db.query(PromptRating).filter(PromptRating.id == rating_id).first()
    if not rating:
        raise HTTPException(status_code=404, detail="Rating not found")
    
    # Check if user already voted
    existing_vote = db.query(RatingHelpfulness).filter(
        RatingHelpfulness.rating_id == rating_id,
        RatingHelpfulness.user_id == current_user.id
    ).first()
    
    if existing_vote:
        # Update existing vote
        if existing_vote.is_helpful != is_helpful:
            # User changed their vote
            if is_helpful:
                rating.helpful_count += 1
                rating.not_helpful_count -= 1
            else:
                rating.helpful_count -= 1
                rating.not_helpful_count += 1
            
            existing_vote.is_helpful = is_helpful
            db.commit()
            
            message = "Vote updated"
        else:
            message = "Vote unchanged"
    else:
        # Create new vote
        vote = RatingHelpfulness(
            rating_id=rating_id,
            user_id=current_user.id,
            is_helpful=is_helpful
        )
        
        db.add(vote)
        
        # Update counts
        if is_helpful:
            rating.helpful_count += 1
        else:
            rating.not_helpful_count += 1
        
        db.commit()
        
        message = "Vote recorded"
    
    # Track event
    await analytics_service.track_event(
        user_id=current_user.id,
        event_type="rating_feedback",
        metadata={
            "rating_id": rating_id,
            "is_helpful": is_helpful,
            "prompt_id": str(rating.prompt_id)
        }
    )
    
    return {
        "message": message,
        "helpful_count": rating.helpful_count,
        "not_helpful_count": rating.not_helpful_count
    }


@router.get("/users/{user_id}/ratings")
async def get_user_ratings(
    user_id: str,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all ratings given by a user"""
    # Check permissions
    if str(current_user.id) != user_id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Get ratings
    query = db.query(PromptRating).join(Prompt).filter(
        PromptRating.user_id == user_id
    ).order_by(
        PromptRating.created_at.desc()
    )
    
    total = query.count()
    ratings = query.offset(offset).limit(limit).all()
    
    # Format response
    rating_list = []
    for rating in ratings:
        prompt = rating.prompt
        rating_list.append({
            "rating_id": str(rating.id),
            "prompt": {
                "id": str(prompt.id),
                "title": prompt.title,
                "category": prompt.category
            },
            "rating": rating.rating,
            "review_title": rating.review_title,
            "review_text": rating.review_text,
            "is_verified_purchase": rating.is_verified_purchase,
            "helpful_count": rating.helpful_count,
            "created_at": rating.created_at.isoformat()
        })
    
    return {
        "ratings": rating_list,
        "total": total,
        "average_rating": db.query(func.avg(PromptRating.rating)).filter(
            PromptRating.user_id == user_id
        ).scalar() or 0,
        "pagination": {
            "limit": limit,
            "offset": offset,
            "total": total
        }
    }


@router.delete("/ratings/{rating_id}")
async def delete_rating(
    rating_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a rating (only by the author)"""
    # Get the rating
    rating = db.query(PromptRating).filter(PromptRating.id == rating_id).first()
    if not rating:
        raise HTTPException(status_code=404, detail="Rating not found")
    
    # Check ownership
    if rating.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Access denied")
    
    prompt_id = rating.prompt_id
    
    # Delete the rating
    db.delete(rating)
    db.commit()
    
    # Update prompt's average rating
    _update_prompt_rating_stats(db, prompt_id)
    
    # Track deletion
    await analytics_service.track_event(
        user_id=current_user.id,
        event_type="rating_deleted",
        metadata={
            "rating_id": rating_id,
            "prompt_id": str(prompt_id)
        }
    )
    
    return {"message": "Rating deleted successfully"}


def _update_prompt_rating_stats(db: Session, prompt_id: str):
    """Update prompt's average rating and count"""
    stats = db.query(
        func.avg(PromptRating.rating).label("avg_rating"),
        func.count(PromptRating.id).label("count")
    ).filter(
        PromptRating.prompt_id == prompt_id
    ).first()
    
    prompt = db.query(Prompt).filter(Prompt.id == prompt_id).first()
    if prompt:
        prompt.rating_average = stats.avg_rating
        prompt.rating_count = stats.count
        db.commit()