from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from datetime import timedelta
from typing import Optional
from api.database import get_db
from api.schemas.user import UserCreate, UserLogin, UserResponse, TokenResponse, PasswordResetRequest, PasswordReset
from api.services.auth_service import AuthService
from api.services.analytics_service import AnalyticsService, EventType
from api.middleware.auth import get_current_active_user
from api.models.user import User
from api.config import settings
from integrations.stripe.client import StripeClient
import logging

logger = logging.getLogger(__name__)
router = APIRouter()
analytics = AnalyticsService()


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    user_data: UserCreate,
    request: Request,
    db: Session = Depends(get_db)
):
    """Register a new user"""
    try:
        # Create user
        user = AuthService.create_user(
            db=db,
            email=user_data.email,
            password=user_data.password,
            company_name=user_data.company_name,
            role=user_data.role.value
        )
        
        # Create Stripe customer
        try:
            stripe_customer_id = await StripeClient.create_customer(
                email=user.email,
                metadata={
                    "user_id": str(user.id),
                    "company_name": user.company_name,
                    "role": user.role.value
                }
            )
            
            # Update user with Stripe customer ID
            user.stripe_customer_id = stripe_customer_id
            db.commit()
            
        except Exception as e:
            logger.error(f"Failed to create Stripe customer for {user.email}: {e}")
            # Continue without Stripe customer ID - can be added later
        
        # Track registration event
        analytics.track_event(
            user_id=str(user.id),
            event_type=EventType.USER_REGISTERED,
            entity_type="user",
            entity_id=str(user.id),
            metadata={
                "company_name": user.company_name,
                "role": user.role.value,
                "ip_address": request.client.host
            }
        )
        
        return UserResponse.from_orm(user)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Registration error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Registration failed"
        )


@router.post("/login", response_model=TokenResponse)
async def login(
    user_credentials: UserLogin,
    request: Request,
    db: Session = Depends(get_db)
):
    """Login and receive access tokens"""
    user = AuthService.authenticate_user(
        db=db,
        email=user_credentials.email,
        password=user_credentials.password
    )
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Create tokens
    access_token = AuthService.create_access_token(
        data={"sub": str(user.id), "email": user.email, "role": user.role.value}
    )
    refresh_token = AuthService.create_refresh_token(
        data={"sub": str(user.id)}
    )
    
    # Track login event
    analytics.track_event(
        user_id=str(user.id),
        event_type=EventType.USER_LOGIN,
        entity_type="user",
        entity_id=str(user.id),
        metadata={
            "ip_address": request.client.host,
            "user_agent": request.headers.get("user-agent")
        }
    )
    
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.access_token_expire_minutes * 60
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    refresh_token: str,
    db: Session = Depends(get_db)
):
    """Refresh access token using refresh token"""
    try:
        payload = AuthService.decode_token(refresh_token)
        
        if payload.get("type") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type"
            )
        
        user_id = payload.get("sub")
        user = db.query(User).filter(User.id == user_id).first()
        
        if not user or user.is_active != "true":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found or inactive"
            )
        
        # Create new access token
        access_token = AuthService.create_access_token(
            data={"sub": str(user.id), "email": user.email, "role": user.role.value}
        )
        
        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,  # Return the same refresh token
            expires_in=settings.access_token_expire_minutes * 60
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token"
        )


@router.get("/profile", response_model=UserResponse)
async def get_profile(
    current_user: User = Depends(get_current_active_user)
):
    """Get current user profile"""
    return UserResponse.from_orm(current_user)


@router.put("/profile", response_model=UserResponse)
async def update_profile(
    company_name: Optional[str] = None,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Update user profile"""
    if company_name:
        current_user.company_name = company_name
    
    db.commit()
    db.refresh(current_user)
    
    return UserResponse.from_orm(current_user)


@router.post("/password-reset/request")
async def request_password_reset(
    request_data: PasswordResetRequest,
    db: Session = Depends(get_db)
):
    """Request password reset token"""
    user = db.query(User).filter(User.email == request_data.email).first()
    
    if user:
        reset_token = AuthService.generate_password_reset_token(user.email)
        # TODO: Send email with reset token
        logger.info(f"Password reset requested for {user.email}")
    
    # Always return success to prevent email enumeration
    return {"message": "If the email exists, a password reset link has been sent"}


@router.post("/password-reset/confirm")
async def confirm_password_reset(
    reset_data: PasswordReset,
    db: Session = Depends(get_db)
):
    """Reset password with token"""
    email = AuthService.verify_password_reset_token(reset_data.token)
    
    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired token"
        )
    
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Update password
    user.password_hash = AuthService.get_password_hash(reset_data.new_password)
    db.commit()
    
    return {"message": "Password reset successful"}