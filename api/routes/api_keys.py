"""
API Key management routes.

Handles creation, listing, and revocation of API keys.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timedelta
import logging

from api.database import get_db
from api.dependencies.auth import get_current_user
from api.models.user import User
from api.models.api_key import APIKey
from api.schemas.api_key import (
    APIKeyCreate,
    APIKeyResponse,
    APIKeyListResponse,
    APIKeyDetailResponse,
    APIKeyUpdate
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/", response_model=APIKeyDetailResponse)
async def create_api_key(
    key_data: APIKeyCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Create a new API key for the authenticated user.
    
    Returns the API key details including the raw key.
    The raw key is only shown once and cannot be retrieved later.
    """
    try:
        # Check if user has reached API key limit (e.g., 10 keys)
        existing_keys = db.query(APIKey).filter(
            APIKey.user_id == current_user.id,
            APIKey.is_active == True
        ).count()
        
        if existing_keys >= 10:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="API key limit reached. Please revoke unused keys."
            )
        
        # Create the API key
        api_key, raw_key = APIKey.create_key(
            user_id=str(current_user.id),
            name=key_data.name,
            description=key_data.description,
            permissions=key_data.permissions.dict() if key_data.permissions else APIKey.DEFAULT_PERMISSIONS,
            expires_at=datetime.utcnow() + timedelta(days=key_data.expires_in_days) if key_data.expires_in_days else None,
            allowed_ips=key_data.allowed_ips or [],
            allowed_endpoints=key_data.allowed_endpoints or [],
            tags=key_data.tags or []
        )
        
        db.add(api_key)
        db.commit()
        db.refresh(api_key)
        
        logger.info(f"Created API key {api_key.id} for user {current_user.id}")
        
        # Return response with raw key
        response = api_key.to_dict(include_sensitive=True)
        response["key"] = raw_key  # Only time the raw key is available
        
        return APIKeyDetailResponse(**response)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating API key: {e}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create API key"
        )


@router.get("/", response_model=List[APIKeyListResponse])
async def list_api_keys(
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    List all API keys for the authenticated user.
    
    Does not return the actual keys, only metadata.
    """
    query = db.query(APIKey).filter(APIKey.user_id == current_user.id)
    
    if is_active is not None:
        query = query.filter(APIKey.is_active == is_active)
    
    api_keys = query.order_by(APIKey.created_at.desc()).all()
    
    return [APIKeyListResponse(**key.to_dict()) for key in api_keys]


@router.get("/{key_id}", response_model=APIKeyResponse)
async def get_api_key(
    key_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get details of a specific API key.
    """
    api_key = db.query(APIKey).filter(
        APIKey.id == key_id,
        APIKey.user_id == current_user.id
    ).first()
    
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found"
        )
    
    return APIKeyResponse(**api_key.to_dict(include_sensitive=True))


@router.patch("/{key_id}", response_model=APIKeyResponse)
async def update_api_key(
    key_id: str,
    update_data: APIKeyUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update an API key's settings.
    
    Can update name, description, permissions, rate limits, etc.
    Cannot update the key itself.
    """
    api_key = db.query(APIKey).filter(
        APIKey.id == key_id,
        APIKey.user_id == current_user.id
    ).first()
    
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found"
        )
    
    if not api_key.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot update revoked API key"
        )
    
    # Update fields
    update_dict = update_data.dict(exclude_unset=True)
    
    for field, value in update_dict.items():
        if field == "permissions" and value is not None:
            setattr(api_key, field, value.dict())
        elif field == "expires_in_days" and value is not None:
            api_key.expires_at = datetime.utcnow() + timedelta(days=value)
        elif hasattr(api_key, field):
            setattr(api_key, field, value)
    
    api_key.updated_at = datetime.utcnow()
    
    try:
        db.commit()
        db.refresh(api_key)
        
        logger.info(f"Updated API key {key_id} for user {current_user.id}")
        
        return APIKeyResponse(**api_key.to_dict(include_sensitive=True))
        
    except Exception as e:
        logger.error(f"Error updating API key: {e}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update API key"
        )


@router.delete("/{key_id}")
async def revoke_api_key(
    key_id: str,
    reason: Optional[str] = Query(None, description="Reason for revocation"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Revoke an API key.
    
    This permanently disables the key and it cannot be re-enabled.
    """
    api_key = db.query(APIKey).filter(
        APIKey.id == key_id,
        APIKey.user_id == current_user.id
    ).first()
    
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found"
        )
    
    if not api_key.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="API key is already revoked"
        )
    
    # Revoke the key
    api_key.revoke(reason=reason or "User requested revocation")
    
    try:
        db.commit()
        
        logger.info(f"Revoked API key {key_id} for user {current_user.id}")
        
        return {
            "message": "API key revoked successfully",
            "key_id": key_id,
            "revoked_at": api_key.revoked_at.isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error revoking API key: {e}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to revoke API key"
        )


@router.post("/{key_id}/rotate", response_model=APIKeyDetailResponse)
async def rotate_api_key(
    key_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Rotate an API key by creating a new one with the same settings
    and revoking the old one.
    
    Returns the new API key with the raw key value.
    """
    # Get the existing key
    old_key = db.query(APIKey).filter(
        APIKey.id == key_id,
        APIKey.user_id == current_user.id
    ).first()
    
    if not old_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found"
        )
    
    if not old_key.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot rotate revoked API key"
        )
    
    try:
        # Create new key with same settings
        new_key, raw_key = APIKey.create_key(
            user_id=str(current_user.id),
            name=f"{old_key.name} (rotated)",
            description=f"Rotated from {old_key.key_prefix}...{old_key.last_four}",
            permissions=old_key.permissions,
            expires_at=old_key.expires_at,
            allowed_ips=old_key.allowed_ips,
            allowed_endpoints=old_key.allowed_endpoints,
            tags=old_key.tags,
            rate_limit=old_key.rate_limit
        )
        
        # Revoke the old key
        old_key.revoke(reason=f"Rotated to new key {new_key.id}")
        
        db.add(new_key)
        db.commit()
        db.refresh(new_key)
        
        logger.info(f"Rotated API key {key_id} to {new_key.id} for user {current_user.id}")
        
        # Return response with raw key
        response = new_key.to_dict(include_sensitive=True)
        response["key"] = raw_key
        response["rotated_from"] = str(old_key.id)
        
        return APIKeyDetailResponse(**response)
        
    except Exception as e:
        logger.error(f"Error rotating API key: {e}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to rotate API key"
        )