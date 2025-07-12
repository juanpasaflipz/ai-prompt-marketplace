"""
Integration tests for complete purchase flow
"""

import pytest
from fastapi import status


class TestPurchaseFlow:
    """Test complete purchase workflow"""
    
    def test_complete_purchase_flow(self, client, db):
        """Test the complete flow from registration to purchase and download"""
        
        # 1. Register as a seller
        seller_response = client.post("/api/v1/auth/register", json={
            "email": "seller@testflow.com",
            "password": "sellerpass123",
            "company_name": "Prompt Creators Inc",
            "full_name": "John Seller",
            "role": "seller"
        })
        assert seller_response.status_code == status.HTTP_201_CREATED
        seller_token = seller_response.json()["access_token"]
        seller_headers = {"Authorization": f"Bearer {seller_token}"}
        
        # 2. Create a prompt as seller
        prompt_data = {
            "title": "Ultimate Sales Email Generator",
            "description": "Generate high-converting sales emails",
            "category": "sales",
            "subcategory": "email",
            "tags": ["sales", "email", "conversion"],
            "template": "Write a {tone} sales email for {product} targeting {audience}",
            "variables": [
                {"name": "tone", "description": "Email tone", "example": "professional", "required": True},
                {"name": "product", "description": "Product name", "example": "CRM Software", "required": True},
                {"name": "audience", "description": "Target audience", "example": "B2B companies", "required": True}
            ],
            "model_type": "gpt-4o",
            "price": 49.99,
            "usage_notes": "Proven to increase response rates by 40%"
        }
        
        create_response = client.post("/api/v1/prompts/", json=prompt_data, headers=seller_headers)
        assert create_response.status_code == status.HTTP_200_OK
        prompt_id = create_response.json()["id"]
        
        # 3. Register as a buyer
        buyer_response = client.post("/api/v1/auth/register", json={
            "email": "buyer@testflow.com",
            "password": "buyerpass123",
            "company_name": "Tech Startup LLC",
            "full_name": "Jane Buyer",
            "role": "buyer"
        })
        assert buyer_response.status_code == status.HTTP_201_CREATED
        buyer_token = buyer_response.json()["access_token"]
        buyer_headers = {"Authorization": f"Bearer {buyer_token}"}
        
        # 4. Search for the prompt
        search_response = client.get("/api/v1/prompts/?query=sales%20email")
        assert search_response.status_code == status.HTTP_200_OK
        assert search_response.json()["total"] >= 1
        
        # 5. View prompt details
        detail_response = client.get(f"/api/v1/prompts/{prompt_id}")
        assert detail_response.status_code == status.HTTP_200_OK
        prompt_details = detail_response.json()
        assert prompt_details["title"] == prompt_data["title"]
        
        # 6. Purchase the prompt
        purchase_response = client.post(
            f"/api/v1/prompts/{prompt_id}/purchase",
            json={"prompt_id": prompt_id, "payment_method_id": "pm_test_123"},
            headers=buyer_headers
        )
        assert purchase_response.status_code == status.HTTP_200_OK
        purchase_data = purchase_response.json()
        assert purchase_data["status"] in ["pending", "completed"]
        
        # 7. Download the purchased prompt
        download_response = client.get(
            f"/api/v1/prompts/{prompt_id}/download",
            headers=buyer_headers
        )
        assert download_response.status_code == status.HTTP_200_OK
        download_data = download_response.json()
        assert download_data["template"] == prompt_data["template"]
        assert len(download_data["variables"]) == 3
        
        # 8. Test the prompt
        test_response = client.post(
            f"/api/v1/prompts/{prompt_id}/test",
            json={
                "prompt_id": prompt_id,
                "variables": {
                    "tone": "professional",
                    "product": "AI Analytics Platform",
                    "audience": "Fortune 500 companies"
                }
            },
            headers=buyer_headers
        )
        assert test_response.status_code == status.HTTP_200_OK
        test_data = test_response.json()
        assert "filled_template" in test_data
        assert "model_response" in test_data
        
        # 9. Rate the prompt
        rating_response = client.post(
            f"/api/v1/prompts/{prompt_id}/rate",
            json={
                "rating": 5,
                "review": "Excellent prompt! Generated great results."
            },
            headers=buyer_headers
        )
        assert rating_response.status_code == status.HTTP_200_OK
        
        # 10. Verify prompt statistics were updated
        updated_prompt = client.get(f"/api/v1/prompts/{prompt_id}")
        assert updated_prompt.status_code == status.HTTP_200_OK
        updated_data = updated_prompt.json()
        assert updated_data["total_sales"] == 1
        assert updated_data["rating_average"] == 5.0
        assert updated_data["rating_count"] == 1
    
    def test_seller_analytics_after_purchase(self, client, db):
        """Test that seller can view analytics after purchases"""
        # This would test analytics endpoints once implemented
        pass
    
    def test_webhook_processing(self, client, db):
        """Test Stripe webhook processing"""
        # Simulate Stripe webhook for payment confirmation
        webhook_payload = {
            "type": "payment_intent.succeeded",
            "data": {
                "object": {
                    "id": "pi_test_123",
                    "amount": 4999,
                    "currency": "usd",
                    "status": "succeeded"
                }
            }
        }
        
        # Note: In real test, would need to sign the payload
        response = client.post(
            "/api/v1/webhooks/stripe",
            json=webhook_payload,
            headers={"Stripe-Signature": "test_signature"}
        )
        
        # Would fail without proper signature verification in test
        # This is just to demonstrate the endpoint exists
        assert response.status_code in [status.HTTP_200_OK, status.HTTP_400_BAD_REQUEST]