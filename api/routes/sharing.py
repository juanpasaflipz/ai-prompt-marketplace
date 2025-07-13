"""
Social sharing endpoints for prompts.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.orm import Session
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
import logging
import urllib.parse

from api.database import get_db
from api.models.user import User
from api.models.prompt import Prompt
from api.models.share import PromptShare
from api.middleware.auth import get_current_user
from api.services.analytics_service import AnalyticsService
from api.services.analytics_funnel import FunnelAnalytics
from api.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()

analytics_service = AnalyticsService()


@router.post("/prompts/{prompt_id}/share")
async def create_share_link(
    prompt_id: str,
    platform: str = Query(..., regex="^(email|twitter|linkedin|facebook|link)$"),
    recipient_email: Optional[str] = Query(None, description="Email for email shares"),
    current_user: Optional[User] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a trackable share link for a prompt"""
    # Get the prompt
    prompt = db.query(Prompt).filter(
        Prompt.id == prompt_id,
        Prompt.is_active == True
    ).first()
    
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")
    
    # Create share record
    share = PromptShare(
        prompt_id=prompt_id,
        user_id=current_user.id if current_user else None,
        share_code=PromptShare.generate_share_code(),
        platform=platform,
        recipient_email=recipient_email if platform == "email" else None,
        expires_at=datetime.utcnow() + timedelta(days=30),  # 30-day expiration
        share_metadata={
            "prompt_title": prompt.title,
            "prompt_category": prompt.category,
            "sharer_name": current_user.full_name if current_user and current_user.full_name else None
        }
    )
    
    db.add(share)
    db.commit()
    db.refresh(share)
    
    # Generate share URL
    base_url = settings.app_base_url  # e.g., https://promptmarketplace.com
    share_url = f"{base_url}/share/{share.share_code}"
    
    # Generate platform-specific share links
    encoded_url = urllib.parse.quote(share_url)
    encoded_title = urllib.parse.quote(f"Check out this AI prompt: {prompt.title}")
    
    platform_urls = {
        "link": share_url,
        "twitter": f"https://twitter.com/intent/tweet?url={encoded_url}&text={encoded_title}",
        "linkedin": f"https://www.linkedin.com/sharing/share-offsite/?url={encoded_url}",
        "facebook": f"https://www.facebook.com/sharer/sharer.php?u={encoded_url}",
        "email": f"mailto:{recipient_email or ''}?subject={encoded_title}&body={encoded_url}"
    }
    
    # Track share event
    if current_user:
        await analytics_service.track_event(
            user_id=current_user.id,
            event_type="prompt_shared",
            prompt_id=prompt_id,
            metadata={
                "platform": platform,
                "share_code": share.share_code
            }
        )
    
    return {
        "share_id": str(share.id),
        "share_code": share.share_code,
        "share_url": share_url,
        "platform_url": platform_urls.get(platform, share_url),
        "expires_at": share.expires_at.isoformat(),
        "platform": platform
    }


@router.get("/share/{share_code}")
async def track_share_click(
    share_code: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Track when someone clicks on a share link and redirect to prompt"""
    # Find the share record
    share = db.query(PromptShare).filter(
        PromptShare.share_code == share_code,
        PromptShare.is_active == True
    ).first()
    
    if not share:
        raise HTTPException(status_code=404, detail="Share link not found")
    
    # Check if expired
    if share.expires_at and share.expires_at < datetime.utcnow():
        raise HTTPException(status_code=410, detail="Share link has expired")
    
    # Get the prompt
    prompt = db.query(Prompt).filter(
        Prompt.id == share.prompt_id,
        Prompt.is_active == True
    ).first()
    
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt no longer available")
    
    # Update click count in background
    def update_click_count():
        share.record_click()
        db.commit()
        
        # Track analytics
        analytics_service.track_event_sync(
            user_id=str(share.user_id) if share.user_id else None,
            event_type="share_clicked",
            prompt_id=share.prompt_id,
            metadata={
                "share_code": share_code,
                "platform": share.platform,
                "total_clicks": share.click_count + 1
            }
        )
    
    background_tasks.add_task(update_click_count)
    
    # Return redirect URL with tracking parameter
    redirect_url = f"{settings.app_base_url}/prompts/{prompt.id}?ref={share_code}"
    
    return {
        "redirect_url": redirect_url,
        "prompt": {
            "id": prompt.id,
            "title": prompt.title,
            "description": prompt.description,
            "price": float(prompt.price),
            "category": prompt.category
        }
    }


@router.post("/share/{share_code}/convert")
async def track_share_conversion(
    share_code: str,
    transaction_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Track when a share leads to a purchase"""
    # Find the share record
    share = db.query(PromptShare).filter(
        PromptShare.share_code == share_code
    ).first()
    
    if not share:
        return {"tracked": False, "reason": "Share not found"}
    
    # Update conversion count
    share.record_conversion()
    db.commit()
    
    # Track analytics
    await analytics_service.track_event(
        user_id=current_user.id,
        event_type="share_converted",
        prompt_id=share.prompt_id,
        metadata={
            "share_code": share_code,
            "platform": share.platform,
            "transaction_id": transaction_id,
            "sharer_id": str(share.user_id) if share.user_id else None
        }
    )
    
    # Could implement referral rewards here
    if share.user_id and share.user_id != current_user.id:
        # Reward the sharer
        await _process_referral_reward(db, share.user_id, transaction_id)
    
    return {
        "tracked": True,
        "message": "Conversion tracked successfully"
    }


@router.get("/users/{user_id}/shares")
async def get_user_shares(
    user_id: str,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get sharing statistics for a user"""
    # Check permissions
    if str(current_user.id) != user_id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Get shares
    shares = db.query(PromptShare).filter(
        PromptShare.user_id == user_id
    ).order_by(
        PromptShare.created_at.desc()
    ).offset(offset).limit(limit).all()
    
    # Calculate totals
    total_shares = db.query(PromptShare).filter(
        PromptShare.user_id == user_id
    ).count()
    
    total_clicks = db.query(
        func.sum(PromptShare.click_count)
    ).filter(
        PromptShare.user_id == user_id
    ).scalar() or 0
    
    total_conversions = db.query(
        func.sum(PromptShare.conversion_count)
    ).filter(
        PromptShare.user_id == user_id
    ).scalar() or 0
    
    # Format response
    share_data = []
    for share in shares:
        prompt = share.prompt
        share_data.append({
            "share_id": str(share.id),
            "prompt": {
                "id": prompt.id,
                "title": prompt.title,
                "category": prompt.category
            },
            "platform": share.platform,
            "clicks": share.click_count,
            "conversions": share.conversion_count,
            "conversion_rate": (share.conversion_count / share.click_count * 100) if share.click_count > 0 else 0,
            "created_at": share.created_at.isoformat()
        })
    
    return {
        "shares": share_data,
        "statistics": {
            "total_shares": total_shares,
            "total_clicks": total_clicks,
            "total_conversions": total_conversions,
            "overall_conversion_rate": (total_conversions / total_clicks * 100) if total_clicks > 0 else 0
        },
        "pagination": {
            "limit": limit,
            "offset": offset,
            "total": total_shares
        }
    }


@router.get("/prompts/{prompt_id}/share-stats")
async def get_prompt_share_stats(
    prompt_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get sharing statistics for a specific prompt"""
    # Get the prompt
    prompt = db.query(Prompt).filter(Prompt.id == prompt_id).first()
    
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")
    
    # Check permissions (owner or admin)
    if prompt.seller_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Get share statistics
    platform_stats = db.query(
        PromptShare.platform,
        func.count(PromptShare.id).label("share_count"),
        func.sum(PromptShare.click_count).label("total_clicks"),
        func.sum(PromptShare.conversion_count).label("total_conversions")
    ).filter(
        PromptShare.prompt_id == prompt_id
    ).group_by(
        PromptShare.platform
    ).all()
    
    # Format platform statistics
    platforms = {}
    total_shares = 0
    total_clicks = 0
    total_conversions = 0
    
    for stat in platform_stats:
        platforms[stat.platform] = {
            "shares": stat.share_count,
            "clicks": stat.total_clicks or 0,
            "conversions": stat.total_conversions or 0,
            "conversion_rate": (stat.total_conversions / stat.total_clicks * 100) if stat.total_clicks else 0
        }
        total_shares += stat.share_count
        total_clicks += stat.total_clicks or 0
        total_conversions += stat.total_conversions or 0
    
    # Get top sharers
    top_sharers = db.query(
        User.id,
        User.email,
        User.full_name,
        func.count(PromptShare.id).label("share_count"),
        func.sum(PromptShare.conversion_count).label("conversions")
    ).join(
        PromptShare, PromptShare.user_id == User.id
    ).filter(
        PromptShare.prompt_id == prompt_id
    ).group_by(
        User.id, User.email, User.full_name
    ).order_by(
        func.sum(PromptShare.conversion_count).desc()
    ).limit(5).all()
    
    return {
        "prompt_id": prompt_id,
        "summary": {
            "total_shares": total_shares,
            "total_clicks": total_clicks,
            "total_conversions": total_conversions,
            "overall_conversion_rate": (total_conversions / total_clicks * 100) if total_clicks > 0 else 0
        },
        "platforms": platforms,
        "top_sharers": [
            {
                "user_id": str(sharer.id),
                "name": sharer.full_name or sharer.email,
                "shares": sharer.share_count,
                "conversions": sharer.conversions
            }
            for sharer in top_sharers
        ]
    }


async def _process_referral_reward(db: Session, referrer_id: str, transaction_id: str):
    """Process referral rewards (placeholder for implementation)"""
    # This could:
    # - Give credits to the referrer
    # - Apply discounts
    # - Track referral metrics
    # - Send notification emails
    pass


# Import required modules
from sqlalchemy import func