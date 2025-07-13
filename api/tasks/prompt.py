"""
Prompt-related background tasks.

Handles asynchronous prompt validation, testing, and metric updates.
"""

from celery import shared_task
from celery.utils.log import get_task_logger
from datetime import datetime
from typing import Dict, Any, Optional
import json
import asyncio
from concurrent.futures import ThreadPoolExecutor

from api.database import get_db
from api.models.prompt import Prompt
from api.models.user import User
from api.services.cache_service import get_cache_service
from api.services.llm_service import LLMService
from api.config import settings

logger = get_task_logger(__name__)
cache = get_cache_service(
    host=settings.redis_host,
    port=settings.redis_port,
    password=settings.redis_password,
    db=settings.redis_db
)


@shared_task(bind=True, max_retries=3)
def validate_prompt_async(self, prompt_id: str, user_id: str):
    """
    Validate a prompt asynchronously.
    
    Checks prompt content, structure, and compliance with marketplace rules.
    """
    try:
        logger.info(f"Starting validation for prompt {prompt_id}")
        
        db = next(get_db())
        
        # Get the prompt
        prompt = db.query(Prompt).filter(Prompt.id == prompt_id).first()
        if not prompt:
            logger.error(f"Prompt {prompt_id} not found")
            return {"status": "failed", "error": "Prompt not found"}
        
        # Initialize validation results
        validation_results = {
            "is_valid": True,
            "errors": [],
            "warnings": [],
            "validated_at": datetime.utcnow().isoformat()
        }
        
        # Check prompt content length
        if len(prompt.content) < 50:
            validation_results["errors"].append("Prompt content is too short (minimum 50 characters)")
            validation_results["is_valid"] = False
        elif len(prompt.content) > 10000:
            validation_results["errors"].append("Prompt content exceeds maximum length (10000 characters)")
            validation_results["is_valid"] = False
        
        # Check for required fields
        if not prompt.title or len(prompt.title) < 5:
            validation_results["errors"].append("Title is missing or too short")
            validation_results["is_valid"] = False
        
        if not prompt.description or len(prompt.description) < 20:
            validation_results["errors"].append("Description is missing or too short")
            validation_results["is_valid"] = False
        
        # Check for prohibited content (placeholder implementation)
        prohibited_terms = ["spam", "illegal", "hack", "crack"]
        content_lower = prompt.content.lower()
        for term in prohibited_terms:
            if term in content_lower:
                validation_results["errors"].append(f"Prohibited content detected: {term}")
                validation_results["is_valid"] = False
        
        # Check prompt structure
        if "{{" in prompt.content and "}}" in prompt.content:
            # Contains variables, check if they're properly formatted
            import re
            variables = re.findall(r'\{\{(\w+)\}\}', prompt.content)
            if variables:
                validation_results["warnings"].append(f"Found {len(variables)} variables: {', '.join(variables)}")
        
        # Update prompt validation status
        if prompt.extra_metadata is None:
            prompt.extra_metadata = {}
        
        prompt.extra_metadata["validation"] = validation_results
        prompt.is_active = validation_results["is_valid"]
        
        db.commit()
        db.close()
        
        # Clear cache
        cache.delete(f"prompt:detail:prompt_id={prompt_id}")
        
        logger.info(f"Validation completed for prompt {prompt_id}: {'PASSED' if validation_results['is_valid'] else 'FAILED'}")
        
        return {
            "status": "success",
            "prompt_id": prompt_id,
            "validation_results": validation_results
        }
        
    except Exception as e:
        logger.error(f"Error validating prompt: {e}")
        raise self.retry(exc=e, countdown=60)


@shared_task(bind=True, max_retries=2)
def test_prompt_async(self, prompt_id: str, test_inputs: Dict[str, Any]):
    """
    Test a prompt with sample inputs asynchronously.
    
    Executes the prompt with provided test inputs and returns the results.
    """
    try:
        logger.info(f"Testing prompt {prompt_id} with inputs: {test_inputs}")
        
        db = next(get_db())
        
        # Get the prompt
        prompt = db.query(Prompt).filter(Prompt.id == prompt_id).first()
        if not prompt:
            logger.error(f"Prompt {prompt_id} not found")
            return {"status": "failed", "error": "Prompt not found"}
        
        # Initialize LLM service
        llm_service = LLMService()
        
        # Prepare the prompt content with test inputs
        test_content = prompt.content
        for key, value in test_inputs.items():
            test_content = test_content.replace(f"{{{{{key}}}}}", str(value))
        
        # Execute the prompt test
        try:
            # Run async function in sync context
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            result = loop.run_until_complete(
                llm_service.test_prompt(
                    content=test_content,
                    model=prompt.model or "gpt-3.5-turbo",
                    max_tokens=prompt.max_tokens or 500
                )
            )
            
            test_result = {
                "status": "success",
                "output": result.get("response", ""),
                "tokens_used": result.get("tokens_used", 0),
                "execution_time": result.get("execution_time", 0),
                "tested_at": datetime.utcnow().isoformat()
            }
            
        except Exception as test_error:
            logger.error(f"Prompt test execution failed: {test_error}")
            test_result = {
                "status": "failed",
                "error": str(test_error),
                "tested_at": datetime.utcnow().isoformat()
            }
        
        # Store test results
        if prompt.extra_metadata is None:
            prompt.extra_metadata = {}
        
        if "test_history" not in prompt.extra_metadata:
            prompt.extra_metadata["test_history"] = []
        
        prompt.extra_metadata["test_history"].append({
            "inputs": test_inputs,
            "result": test_result
        })
        
        # Keep only last 10 test results
        prompt.extra_metadata["test_history"] = prompt.extra_metadata["test_history"][-10:]
        
        db.commit()
        db.close()
        
        logger.info(f"Test completed for prompt {prompt_id}: {test_result['status']}")
        
        return {
            "status": "success",
            "prompt_id": prompt_id,
            "test_result": test_result
        }
        
    except Exception as e:
        logger.error(f"Error testing prompt: {e}")
        raise self.retry(exc=e, countdown=30)


@shared_task(bind=True)
def generate_prompt_preview(self, prompt_id: str):
    """
    Generate a preview/thumbnail for a prompt.
    
    Creates a visual representation or summary of the prompt for display.
    """
    try:
        logger.info(f"Generating preview for prompt {prompt_id}")
        
        db = next(get_db())
        
        # Get the prompt
        prompt = db.query(Prompt).filter(Prompt.id == prompt_id).first()
        if not prompt:
            logger.error(f"Prompt {prompt_id} not found")
            return {"status": "failed", "error": "Prompt not found"}
        
        # Generate preview data
        preview = {
            "title": prompt.title,
            "description": prompt.description[:200] + "..." if len(prompt.description) > 200 else prompt.description,
            "snippet": prompt.content[:150] + "..." if len(prompt.content) > 150 else prompt.content,
            "category": prompt.category,
            "tags": prompt.tags or [],
            "variables": [],
            "estimated_tokens": len(prompt.content.split()) * 1.3,  # Rough estimate
            "generated_at": datetime.utcnow().isoformat()
        }
        
        # Extract variables from content
        import re
        variables = re.findall(r'\{\{(\w+)\}\}', prompt.content)
        if variables:
            preview["variables"] = list(set(variables))
        
        # Store preview
        if prompt.extra_metadata is None:
            prompt.extra_metadata = {}
        
        prompt.extra_metadata["preview"] = preview
        
        db.commit()
        db.close()
        
        # Cache the preview
        cache.set(f"prompt:preview:{prompt_id}", preview, ttl=3600)  # 1 hour
        
        logger.info(f"Preview generated for prompt {prompt_id}")
        
        return {
            "status": "success",
            "prompt_id": prompt_id,
            "preview": preview
        }
        
    except Exception as e:
        logger.error(f"Error generating prompt preview: {e}")
        raise


@shared_task(bind=True)
def update_prompt_metrics(self, prompt_id: str):
    """
    Update various metrics for a prompt.
    
    Calculates and updates performance metrics, ratings, and usage statistics.
    """
    try:
        logger.info(f"Updating metrics for prompt {prompt_id}")
        
        db = next(get_db())
        
        # Get the prompt
        prompt = db.query(Prompt).filter(Prompt.id == prompt_id).first()
        if not prompt:
            logger.error(f"Prompt {prompt_id} not found")
            return {"status": "failed", "error": "Prompt not found"}
        
        # Calculate metrics (placeholder implementation)
        from sqlalchemy import func
        from api.models.analytics import AnalyticsEvent
        from api.models.transaction import Transaction
        from api.models.review import Review
        
        # View count from analytics
        view_count = db.query(func.count(AnalyticsEvent.id)).filter(
            AnalyticsEvent.event_type == 'prompt_viewed',
            AnalyticsEvent.event_metadata['prompt_id'].astext == str(prompt_id)
        ).scalar() or 0
        
        # Purchase count
        purchase_count = db.query(func.count(Transaction.id)).filter(
            Transaction.prompt_id == prompt_id,
            Transaction.status == 'completed'
        ).scalar() or 0
        
        # Average rating
        avg_rating = db.query(func.avg(Review.rating)).filter(
            Review.prompt_id == prompt_id
        ).scalar() or 0
        
        # Total reviews
        review_count = db.query(func.count(Review.id)).filter(
            Review.prompt_id == prompt_id
        ).scalar() or 0
        
        # Update metrics
        metrics = {
            "view_count": view_count,
            "purchase_count": purchase_count,
            "conversion_rate": round((purchase_count / view_count * 100) if view_count > 0 else 0, 2),
            "average_rating": round(float(avg_rating), 2),
            "review_count": review_count,
            "popularity_score": view_count + (purchase_count * 10) + (avg_rating * review_count),
            "last_updated": datetime.utcnow().isoformat()
        }
        
        if prompt.extra_metadata is None:
            prompt.extra_metadata = {}
        
        prompt.extra_metadata["metrics"] = metrics
        
        db.commit()
        db.close()
        
        # Clear caches
        cache.delete(f"prompt:detail:prompt_id={prompt_id}")
        cache.delete(f"prompt:metrics:{prompt_id}")
        
        logger.info(f"Metrics updated for prompt {prompt_id}: {metrics}")
        
        return {
            "status": "success",
            "prompt_id": prompt_id,
            "metrics": metrics
        }
        
    except Exception as e:
        logger.error(f"Error updating prompt metrics: {e}")
        raise