"""
Unit tests for prompt endpoints
"""

import pytest
from fastapi import status
from decimal import Decimal


class TestPromptEndpoints:
    """Test prompt CRUD operations"""
    
    def test_create_prompt_as_seller(self, client, test_seller, seller_auth_headers):
        """Test creating a prompt as a seller"""
        prompt_data = {
            "title": "New Sales Prompt",
            "description": "Generate compelling sales emails",
            "category": "sales",
            "subcategory": "email",
            "tags": ["sales", "email", "b2b"],
            "template": "Write a {tone} sales email for {product}",
            "variables": [
                {"name": "tone", "description": "Email tone", "example": "professional", "required": True},
                {"name": "product", "description": "Product name", "example": "SaaS tool", "required": True}
            ],
            "model_type": "gpt-4o",
            "price": 29.99,
            "usage_notes": "Best for B2B sales"
        }
        
        response = client.post("/api/v1/prompts/", json=prompt_data, headers=seller_auth_headers)
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["title"] == prompt_data["title"]
        assert data["seller_id"] == test_seller.id
        assert data["is_active"] is True
        assert data["total_sales"] == 0
    
    def test_create_prompt_as_buyer_fails(self, client, auth_headers):
        """Test that buyers cannot create prompts"""
        prompt_data = {
            "title": "Test Prompt",
            "description": "Test",
            "category": "sales",
            "template": "Test template",
            "model_type": "gpt-4o",
            "price": 19.99
        }
        
        response = client.post("/api/v1/prompts/", json=prompt_data, headers=auth_headers)
        
        assert response.status_code == status.HTTP_403_FORBIDDEN
    
    def test_list_prompts(self, client, test_prompt):
        """Test listing prompts"""
        response = client.get("/api/v1/prompts/")
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["total"] >= 1
        assert len(data["prompts"]) >= 1
        assert data["prompts"][0]["id"] == test_prompt.id
    
    def test_search_prompts(self, client, test_prompt):
        """Test searching prompts"""
        # Search by query
        response = client.get("/api/v1/prompts/?query=test")
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["total"] >= 1
        
        # Search by category
        response = client.get(f"/api/v1/prompts/?category={test_prompt.category}")
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["total"] >= 1
        
        # Search by price range
        response = client.get("/api/v1/prompts/?min_price=10&max_price=30")
        assert response.status_code == status.HTTP_200_OK
    
    def test_get_prompt_by_id(self, client, test_prompt):
        """Test getting a specific prompt"""
        response = client.get(f"/api/v1/prompts/{test_prompt.id}")
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["id"] == test_prompt.id
        assert data["title"] == test_prompt.title
    
    def test_update_prompt_as_owner(self, client, test_prompt, seller_auth_headers):
        """Test updating own prompt"""
        update_data = {
            "title": "Updated Prompt Title",
            "price": 39.99
        }
        
        response = client.put(
            f"/api/v1/prompts/{test_prompt.id}", 
            json=update_data, 
            headers=seller_auth_headers
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["title"] == update_data["title"]
        assert float(data["price"]) == update_data["price"]
    
    def test_update_prompt_as_non_owner_fails(self, client, test_prompt, auth_headers):
        """Test that non-owners cannot update prompts"""
        update_data = {"title": "Hacked Title"}
        
        response = client.put(
            f"/api/v1/prompts/{test_prompt.id}", 
            json=update_data, 
            headers=auth_headers
        )
        
        assert response.status_code == status.HTTP_403_FORBIDDEN
    
    def test_delete_prompt(self, client, test_prompt, seller_auth_headers):
        """Test deleting a prompt (soft delete)"""
        response = client.delete(
            f"/api/v1/prompts/{test_prompt.id}", 
            headers=seller_auth_headers
        )
        
        assert response.status_code == status.HTTP_200_OK
        
        # Verify prompt is soft deleted
        get_response = client.get(f"/api/v1/prompts/{test_prompt.id}")
        assert get_response.status_code == status.HTTP_404_NOT_FOUND
    
    def test_purchase_prompt(self, client, test_prompt, auth_headers):
        """Test purchasing a prompt"""
        purchase_data = {
            "prompt_id": test_prompt.id,
            "payment_method_id": "pm_test_123"
        }
        
        response = client.post(
            f"/api/v1/prompts/{test_prompt.id}/purchase",
            json=purchase_data,
            headers=auth_headers
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["prompt_id"] == test_prompt.id
        assert data["status"] in ["pending", "completed"]
        assert "download_url" in data
    
    def test_purchase_prompt_twice_fails(self, client, test_prompt, test_user, auth_headers, db):
        """Test that users cannot purchase the same prompt twice"""
        from api.models.transaction import Transaction
        
        # Create existing purchase
        transaction = Transaction(
            buyer_id=test_user.id,
            seller_id=test_prompt.seller_id,
            prompt_id=test_prompt.id,
            amount=test_prompt.price,
            status="completed"
        )
        db.add(transaction)
        db.commit()
        
        # Try to purchase again
        purchase_data = {"prompt_id": test_prompt.id}
        response = client.post(
            f"/api/v1/prompts/{test_prompt.id}/purchase",
            json=purchase_data,
            headers=auth_headers
        )
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "already purchased" in response.json()["detail"]
    
    def test_download_purchased_prompt(self, client, test_prompt, test_user, auth_headers, db):
        """Test downloading a purchased prompt"""
        from api.models.transaction import Transaction
        
        # Create purchase record
        transaction = Transaction(
            buyer_id=test_user.id,
            seller_id=test_prompt.seller_id,
            prompt_id=test_prompt.id,
            amount=test_prompt.price,
            status="completed"
        )
        db.add(transaction)
        db.commit()
        
        # Download prompt
        response = client.get(
            f"/api/v1/prompts/{test_prompt.id}/download",
            headers=auth_headers
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["prompt_id"] == test_prompt.id
        assert data["template"] == test_prompt.template
        assert "variables" in data
    
    def test_download_unpurchased_prompt_fails(self, client, test_prompt, auth_headers):
        """Test that users cannot download unpurchased prompts"""
        response = client.get(
            f"/api/v1/prompts/{test_prompt.id}/download",
            headers=auth_headers
        )
        
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "not purchased" in response.json()["detail"]
    
    def test_rate_prompt(self, client, test_prompt, test_user, auth_headers, db):
        """Test rating a purchased prompt"""
        from api.models.transaction import Transaction
        
        # Create purchase record
        transaction = Transaction(
            buyer_id=test_user.id,
            seller_id=test_prompt.seller_id,
            prompt_id=test_prompt.id,
            amount=test_prompt.price,
            status="completed"
        )
        db.add(transaction)
        db.commit()
        
        # Rate prompt
        rating_data = {
            "rating": 5,
            "review": "Excellent prompt!"
        }
        
        response = client.post(
            f"/api/v1/prompts/{test_prompt.id}/rate",
            json=rating_data,
            headers=auth_headers
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["rating"] == 5
        assert data["review"] == "Excellent prompt!"