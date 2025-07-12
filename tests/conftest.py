"""
Test configuration and fixtures
"""

import pytest
import asyncio
from typing import Generator, AsyncGenerator
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool
import os

# Set test environment
os.environ["ENVIRONMENT"] = "test"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["JWT_SECRET_KEY"] = "test-secret-key"
os.environ["STRIPE_SECRET_KEY"] = "sk_test_dummy"
os.environ["OPENAI_API_KEY"] = "sk-test-dummy"
os.environ["SECRET_KEY"] = "test-secret"
os.environ["REDIS_URL"] = "redis://localhost:6379/1"

from api.database import Base, get_db
from api.main import app
from api.models.user import User
from api.models.prompt import Prompt
from api.services.auth_service import AuthService


# Create test engine
engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="function")
def db() -> Generator[Session, None, None]:
    """Create a new database session for each test."""
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client(db: Session) -> Generator[TestClient, None, None]:
    """Create a test client with database override."""
    
    def override_get_db():
        try:
            yield db
        finally:
            pass
    
    app.dependency_overrides[get_db] = override_get_db
    
    with TestClient(app) as test_client:
        yield test_client
    
    app.dependency_overrides.clear()


@pytest.fixture
def test_user(db: Session) -> User:
    """Create a test user."""
    user = User(
        email="test@example.com",
        role="buyer",
        company_name="Test Company",
        full_name="Test User",
        stripe_customer_id="cus_test123"
    )
    user.password_hash = AuthService.hash_password("password123")
    
    db.add(user)
    db.commit()
    db.refresh(user)
    
    return user


@pytest.fixture
def test_seller(db: Session) -> User:
    """Create a test seller."""
    seller = User(
        email="seller@example.com",
        role="seller",
        company_name="Seller Company",
        full_name="Test Seller",
        stripe_customer_id="cus_test456"
    )
    seller.password_hash = AuthService.hash_password("password123")
    
    db.add(seller)
    db.commit()
    db.refresh(seller)
    
    return seller


@pytest.fixture
def test_admin(db: Session) -> User:
    """Create a test admin."""
    admin = User(
        email="admin@example.com",
        role="admin",
        company_name="Admin Company",
        full_name="Test Admin",
        stripe_customer_id="cus_test789"
    )
    admin.password_hash = AuthService.hash_password("adminpass")
    
    db.add(admin)
    db.commit()
    db.refresh(admin)
    
    return admin


@pytest.fixture
def test_prompt(db: Session, test_seller: User) -> Prompt:
    """Create a test prompt."""
    prompt = Prompt(
        seller_id=test_seller.id,
        title="Test Prompt",
        description="This is a test prompt",
        category="sales",
        subcategory="email",
        tags=["test", "email"],
        template="Write a {tone} email about {topic}",
        variables=[
            {"name": "tone", "description": "Email tone", "example": "professional"},
            {"name": "topic", "description": "Email topic", "example": "product launch"}
        ],
        model_type="gpt-4o",
        price=19.99,
        usage_notes="Test usage notes"
    )
    
    db.add(prompt)
    db.commit()
    db.refresh(prompt)
    
    return prompt


@pytest.fixture
def auth_headers(test_user: User) -> dict:
    """Create authentication headers for test user."""
    access_token = AuthService.create_access_token(
        data={"sub": test_user.email, "user_id": test_user.id, "role": test_user.role}
    )
    return {"Authorization": f"Bearer {access_token}"}


@pytest.fixture
def seller_auth_headers(test_seller: User) -> dict:
    """Create authentication headers for test seller."""
    access_token = AuthService.create_access_token(
        data={"sub": test_seller.email, "user_id": test_seller.id, "role": test_seller.role}
    )
    return {"Authorization": f"Bearer {access_token}"}


@pytest.fixture
def admin_auth_headers(test_admin: User) -> dict:
    """Create authentication headers for test admin."""
    access_token = AuthService.create_access_token(
        data={"sub": test_admin.email, "user_id": test_admin.id, "role": test_admin.role}
    )
    return {"Authorization": f"Bearer {access_token}"}


# Mock external services
class MockStripeClient:
    @staticmethod
    async def create_customer(email: str, name: str = None, metadata: dict = None):
        return f"cus_test_{email.split('@')[0]}"
    
    @staticmethod
    async def create_payment_intent(amount, customer_id, payment_method_id=None, metadata=None):
        return {
            "id": "pi_test_123",
            "client_secret": "pi_test_123_secret",
            "status": "succeeded" if payment_method_id else "requires_payment_method",
            "amount": amount * 100 if amount < 1000 else amount,
            "currency": "usd",
            "receipt_url": None
        }


class MockOpenAIClient:
    @staticmethod
    async def test_prompt(prompt: str, model: str = "gpt-4o"):
        return {
            "response": "This is a test response to the prompt.",
            "tokens_used": 150,
            "response_time_ms": 500,
            "estimated_cost": 0.05,
            "model": model,
            "prompt_tokens": 50,
            "completion_tokens": 100
        }
    
    @staticmethod
    async def validate_prompt(template: str, variables: list):
        return {
            "is_valid": True,
            "estimated_tokens": 100,
            "cost_estimates": {
                "gpt-4o": {"min": 0.01, "max": 0.05, "average": 0.03}
            },
            "sample_prompt": template
        }


@pytest.fixture(autouse=True)
def mock_external_services(monkeypatch):
    """Mock external services for all tests."""
    monkeypatch.setattr("integrations.stripe.client.StripeClient", MockStripeClient)
    monkeypatch.setattr("integrations.openai.client.OpenAIClient", MockOpenAIClient)