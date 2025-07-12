"""
Unit tests for marketplace endpoints
"""

import pytest
from fastapi import status


class TestMarketplaceEndpoints:
    """Test marketplace browsing and discovery"""
    
    def test_get_categories(self, client, test_prompt):
        """Test getting prompt categories"""
        response = client.get("/api/v1/marketplace/categories")
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "categories" in data
        assert len(data["categories"]) > 0
        
        # Check if test prompt's category is included
        categories = [cat["name"] for cat in data["categories"]]
        assert test_prompt.category in categories
    
    def test_get_subcategories(self, client, test_prompt):
        """Test getting subcategories for a category"""
        response = client.get(f"/api/v1/marketplace/subcategories?category={test_prompt.category}")
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["category"] == test_prompt.category
        assert "subcategories" in data
    
    def test_get_trending_prompts(self, client, test_prompt):
        """Test getting trending prompts"""
        response = client.get("/api/v1/marketplace/trending?limit=10&timeframe=week")
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["timeframe"] == "week"
        assert "prompts" in data
        assert isinstance(data["prompts"], list)
    
    def test_get_featured_prompts(self, client, db, test_seller):
        """Test getting featured prompts"""
        from api.models.prompt import Prompt
        
        # Create a highly-rated prompt
        featured_prompt = Prompt(
            seller_id=test_seller.id,
            title="Featured Prompt",
            description="High-quality prompt",
            category="marketing",
            template="Template",
            model_type="gpt-4o",
            price=49.99,
            total_sales=10,
            rating_average=4.8,
            rating_count=8
        )
        db.add(featured_prompt)
        db.commit()
        
        response = client.get("/api/v1/marketplace/featured?limit=5")
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "prompts" in data
        assert len(data["prompts"]) > 0
        
        # Verify featured prompt is included
        prompt_ids = [p["id"] for p in data["prompts"]]
        assert featured_prompt.id in prompt_ids
    
    def test_get_marketplace_statistics(self, client, test_prompt):
        """Test getting marketplace statistics"""
        response = client.get("/api/v1/marketplace/statistics")
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "total_prompts" in data
        assert "total_sellers" in data
        assert "total_transactions" in data
        assert "average_price" in data
        assert "top_categories" in data
        
        assert data["total_prompts"] >= 1
        assert data["total_sellers"] >= 1
    
    def test_get_seller_profile(self, client, test_seller, test_prompt, auth_headers):
        """Test getting seller profile"""
        response = client.get(
            f"/api/v1/marketplace/sellers/{test_seller.id}",
            headers=auth_headers
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        
        assert "seller" in data
        assert data["seller"]["id"] == test_seller.id
        assert data["seller"]["company"] == test_seller.company_name
        assert data["seller"]["total_prompts"] >= 1
        
        assert "prompts" in data
        assert len(data["prompts"]) >= 1
    
    def test_get_nonexistent_seller_profile(self, client):
        """Test getting profile of non-existent seller"""
        response = client.get("/api/v1/marketplace/sellers/99999")
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["error"] == "Seller not found"
    
    def test_trending_with_different_timeframes(self, client):
        """Test trending endpoints with different timeframes"""
        timeframes = ["day", "week", "month"]
        
        for timeframe in timeframes:
            response = client.get(f"/api/v1/marketplace/trending?timeframe={timeframe}")
            assert response.status_code == status.HTTP_200_OK
            assert response.json()["timeframe"] == timeframe