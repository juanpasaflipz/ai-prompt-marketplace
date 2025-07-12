"""
Unit tests for authentication
"""

import pytest
from fastapi import status
from datetime import datetime, timedelta
from jose import jwt

from api.config import settings
from api.services.auth_service import AuthService


class TestAuthService:
    """Test authentication service methods"""
    
    def test_password_hashing(self):
        """Test password hashing and verification"""
        password = "testpassword123"
        
        # Hash password
        hashed = AuthService.hash_password(password)
        
        # Verify correct password
        assert AuthService.verify_password(password, hashed) is True
        
        # Verify incorrect password
        assert AuthService.verify_password("wrongpassword", hashed) is False
    
    def test_create_access_token(self):
        """Test access token creation"""
        data = {"sub": "test@example.com", "user_id": 1, "role": "buyer"}
        
        token = AuthService.create_access_token(data)
        
        # Decode token
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        
        assert payload["sub"] == "test@example.com"
        assert payload["user_id"] == 1
        assert payload["role"] == "buyer"
        assert payload["type"] == "access"
        assert "exp" in payload
    
    def test_create_refresh_token(self):
        """Test refresh token creation"""
        data = {"sub": "test@example.com", "user_id": 1}
        
        token = AuthService.create_refresh_token(data)
        
        # Decode token
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        
        assert payload["sub"] == "test@example.com"
        assert payload["user_id"] == 1
        assert payload["type"] == "refresh"
        assert "exp" in payload
    
    def test_decode_token(self):
        """Test token decoding"""
        data = {"sub": "test@example.com", "user_id": 1}
        token = AuthService.create_access_token(data)
        
        # Decode valid token
        payload = AuthService.decode_token(token)
        assert payload is not None
        assert payload["sub"] == "test@example.com"
        
        # Test invalid token
        invalid_token = "invalid.token.here"
        assert AuthService.decode_token(invalid_token) is None
        
        # Test expired token
        expired_data = data.copy()
        expired_data["exp"] = datetime.utcnow() - timedelta(hours=1)
        expired_token = jwt.encode(expired_data, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
        assert AuthService.decode_token(expired_token) is None


class TestAuthEndpoints:
    """Test authentication API endpoints"""
    
    def test_register_success(self, client):
        """Test successful user registration"""
        response = client.post("/api/v1/auth/register", json={
            "email": "newuser@example.com",
            "password": "password123",
            "company_name": "New Company",
            "full_name": "New User",
            "role": "buyer"
        })
        
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["email"] == "newuser@example.com"
        assert data["company_name"] == "New Company"
        assert "access_token" in data
        assert "refresh_token" in data
        assert "token_type" in data
    
    def test_register_duplicate_email(self, client, test_user):
        """Test registration with duplicate email"""
        response = client.post("/api/v1/auth/register", json={
            "email": test_user.email,
            "password": "password123",
            "company_name": "Another Company",
            "role": "buyer"
        })
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "already registered" in response.json()["detail"]
    
    def test_login_success(self, client, test_user):
        """Test successful login"""
        response = client.post("/api/v1/auth/login", data={
            "username": test_user.email,
            "password": "password123"
        })
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"
    
    def test_login_invalid_credentials(self, client, test_user):
        """Test login with invalid credentials"""
        response = client.post("/api/v1/auth/login", data={
            "username": test_user.email,
            "password": "wrongpassword"
        })
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert response.json()["detail"] == "Invalid credentials"
    
    def test_login_nonexistent_user(self, client):
        """Test login with non-existent user"""
        response = client.post("/api/v1/auth/login", data={
            "username": "nonexistent@example.com",
            "password": "password123"
        })
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert response.json()["detail"] == "Invalid credentials"
    
    def test_refresh_token(self, client, test_user):
        """Test token refresh"""
        # First login to get tokens
        login_response = client.post("/api/v1/auth/login", data={
            "username": test_user.email,
            "password": "password123"
        })
        refresh_token = login_response.json()["refresh_token"]
        
        # Use refresh token
        response = client.post("/api/v1/auth/refresh", json={
            "refresh_token": refresh_token
        })
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
    
    def test_refresh_invalid_token(self, client):
        """Test refresh with invalid token"""
        response = client.post("/api/v1/auth/refresh", json={
            "refresh_token": "invalid.refresh.token"
        })
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert response.json()["detail"] == "Invalid refresh token"
    
    def test_get_current_user(self, client, test_user, auth_headers):
        """Test getting current user info"""
        response = client.get("/api/v1/auth/me", headers=auth_headers)
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["email"] == test_user.email
        assert data["company_name"] == test_user.company_name
        assert "password_hash" not in data
    
    def test_get_current_user_no_auth(self, client):
        """Test getting current user without authentication"""
        response = client.get("/api/v1/auth/me")
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert response.json()["detail"] == "Not authenticated"