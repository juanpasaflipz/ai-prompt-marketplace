from pydantic import BaseModel, EmailStr, Field, validator
from typing import Optional
from datetime import datetime
from api.models.user import UserRole, SubscriptionStatus


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=100)
    company_name: str = Field(..., min_length=2, max_length=255)
    role: UserRole = UserRole.BUYER

    @validator('password')
    def validate_password(cls, v):
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters long')
        if not any(char.isdigit() for char in v):
            raise ValueError('Password must contain at least one digit')
        if not any(char.isupper() for char in v):
            raise ValueError('Password must contain at least one uppercase letter')
        return v


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: str
    email: EmailStr
    company_name: str
    role: UserRole
    subscription_status: SubscriptionStatus
    is_active: str
    created_at: datetime

    class Config:
        from_attributes = True
        
    @classmethod
    def from_orm(cls, user):
        return cls(
            id=str(user.id),
            email=user.email,
            company_name=user.company_name,
            role=user.role,
            subscription_status=user.subscription_status,
            is_active=user.is_active,
            created_at=user.created_at
        )


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordReset(BaseModel):
    token: str
    new_password: str = Field(..., min_length=8, max_length=100)