from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_, or_, func
from typing import List, Optional, Any
import logging

from api.database import get_db
from api.models.user import User
from api.models.prompt import Prompt
from api.models.transaction import Transaction
from api.schemas.prompt import (
    PromptCreate,
    PromptUpdate,
    PromptResponse,
    PromptListResponse,
    PromptSearchParams,
    PromptPurchaseRequest,
    PromptPurchaseResponse,
    PromptRatingRequest,
    PromptRatingResponse,
    PromptTestRequest,
    PromptTestResponse,
)
from api.middleware.auth import get_current_user, require_role
from api.services.analytics_service import AnalyticsService
from api.services.cache_service import get_cache_service
from api.config import settings
from integrations.stripe.client import StripeClient
from integrations.openai.client import OpenAIClient

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/prompts", tags=["prompts"])

analytics_service = AnalyticsService()
stripe_client = StripeClient()
openai_client = OpenAIClient()

# Initialize cache service
cache = get_cache_service(
    host=settings.redis_host,
    port=settings.redis_port,
    password=settings.redis_password,
    db=settings.redis_db,
    decode_responses=settings.redis_decode_responses
)


def safe_cache_get(key: str, default=None):
    """Safely get value from cache with error handling"""
    try:
        return cache.get(key) if settings.cache_enabled else default
    except Exception as e:
        logger.warning(f"Cache get failed for key {key}: {e}")
        return default


def safe_cache_set(key: str, value: Any, ttl: Optional[int] = None) -> bool:
    """Safely set value in cache with error handling"""
    try:
        return cache.set(key, value, ttl=ttl) if settings.cache_enabled else False
    except Exception as e:
        logger.warning(f"Cache set failed for key {key}: {e}")
        return False


def safe_cache_delete(*keys: str) -> int:
    """Safely delete keys from cache with error handling"""
    try:
        return cache.delete(*keys) if settings.cache_enabled else 0
    except Exception as e:
        logger.warning(f"Cache delete failed for keys {keys}: {e}")
        return 0


def safe_cache_clear_pattern(pattern: str) -> int:
    """Safely clear cache pattern with error handling"""
    try:
        return cache.clear_pattern(pattern) if settings.cache_enabled else 0
    except Exception as e:
        logger.warning(f"Cache clear pattern failed for {pattern}: {e}")
        return 0


@router.post("/", response_model=PromptResponse)
async def create_prompt(
    prompt_data: PromptCreate,
    current_user: User = Depends(require_role(["seller", "admin"])),
    db: Session = Depends(get_db)
):
    """Create a new prompt (sellers only)"""
    try:
        # Create the prompt
        prompt = Prompt(
            seller_id=current_user.id,
            **prompt_data.model_dump()
        )
        
        db.add(prompt)
        db.commit()
        db.refresh(prompt)
        
        # Invalidate prompt list caches since a new prompt was created
        safe_cache_clear_pattern("prompts:list*")
        logger.debug(f"Invalidated prompt list cache after creating prompt {prompt.id}")
        
        # Track analytics
        await analytics_service.track_event(
            user_id=current_user.id,
            event_type="prompt_created",
            prompt_id=prompt.id,
            metadata={"category": prompt.category, "price": float(prompt.price)}
        )
        
        # Prepare response with seller info
        response = PromptResponse(
            **prompt.to_dict(),
            seller_name=current_user.full_name or current_user.email,
            seller_company=current_user.company_name
        )
        
        return response
        
    except Exception as e:
        logger.error(f"Error creating prompt: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to create prompt")


@router.get("/", response_model=PromptListResponse)
async def list_prompts(
    search_params: PromptSearchParams = Depends(),
    current_user: Optional[User] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List and search prompts with filtering"""
    try:
        # Generate cache key based on search parameters
        cache_key = cache.generate_key(
            "prompts:list",
            query=search_params.query,
            category=search_params.category,
            subcategory=search_params.subcategory,
            tags=",".join(search_params.tags) if search_params.tags else None,
            min_price=search_params.min_price,
            max_price=search_params.max_price,
            model_type=search_params.model_type,
            seller_id=search_params.seller_id,
            sort_by=search_params.sort_by,
            sort_order=search_params.sort_order,
            page=search_params.page,
            per_page=search_params.per_page
        )
        
        # Try to get from cache first
        cached_result = safe_cache_get(cache_key)
        if cached_result is not None:
            logger.debug(f"Cache hit for prompts list: {cache_key}")
            # Still track analytics for cached results
            if current_user:
                await analytics_service.track_event(
                    user_id=current_user.id,
                    event_type="prompts_searched",
                    metadata={
                        "query": search_params.query,
                        "category": search_params.category,
                        "results_count": len(cached_result.get("prompts", [])),
                        "from_cache": True
                    }
                )
            return PromptListResponse(**cached_result)
        
        logger.debug(f"Cache miss for prompts list: {cache_key}")
        # Build query
        query = db.query(Prompt).join(User).filter(Prompt.is_active == True)
        
        # Apply filters
        if search_params.query:
            search_term = f"%{search_params.query}%"
            query = query.filter(
                or_(
                    Prompt.title.ilike(search_term),
                    Prompt.description.ilike(search_term),
                    func.array_to_string(Prompt.tags, ',').ilike(search_term)
                )
            )
        
        if search_params.category:
            query = query.filter(Prompt.category == search_params.category)
        
        if search_params.subcategory:
            query = query.filter(Prompt.subcategory == search_params.subcategory)
        
        if search_params.tags:
            query = query.filter(Prompt.tags.overlap(search_params.tags))
        
        if search_params.min_price is not None:
            query = query.filter(Prompt.price >= search_params.min_price)
        
        if search_params.max_price is not None:
            query = query.filter(Prompt.price <= search_params.max_price)
        
        if search_params.model_type:
            query = query.filter(Prompt.model_type == search_params.model_type)
        
        if search_params.seller_id:
            query = query.filter(Prompt.seller_id == search_params.seller_id)
        
        # Apply sorting
        order_by = getattr(Prompt, search_params.sort_by)
        if search_params.sort_order == "desc":
            order_by = order_by.desc()
        query = query.order_by(order_by)
        
        # Pagination
        total = query.count()
        prompts = query.offset((search_params.page - 1) * search_params.per_page).limit(search_params.per_page).all()
        
        # Track analytics
        if current_user:
            await analytics_service.track_event(
                user_id=current_user.id,
                event_type="prompts_searched",
                metadata={
                    "query": search_params.query,
                    "category": search_params.category,
                    "results_count": len(prompts)
                }
            )
        
        # Prepare response
        prompt_responses = []
        for prompt in prompts:
            prompt_responses.append(PromptResponse(
                **prompt.to_dict(),
                seller_name=prompt.seller.full_name or prompt.seller.email,
                seller_company=prompt.seller.company_name
            ))
        
        response = PromptListResponse(
            prompts=prompt_responses,
            total=total,
            page=search_params.page,
            per_page=search_params.per_page,
            pages=(total + search_params.per_page - 1) // search_params.per_page
        )
        
        # Cache the result with 30-minute TTL
        cache_data = response.model_dump()
        safe_cache_set(cache_key, cache_data, ttl=settings.cache_prompt_ttl)
        logger.debug(f"Cached prompts list result: {cache_key}")
        
        return response
        
    except Exception as e:
        logger.error(f"Error listing prompts: {e}")
        raise HTTPException(status_code=500, detail="Failed to list prompts")


@router.get("/{prompt_id}", response_model=PromptResponse)
async def get_prompt(
    prompt_id: int,
    current_user: Optional[User] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get a specific prompt by ID"""
    # Generate cache key
    cache_key = cache.generate_key("prompt:detail", prompt_id=prompt_id)
    
    # Try to get from cache first
    cached_result = safe_cache_get(cache_key)
    if cached_result is not None:
        logger.debug(f"Cache hit for prompt {prompt_id}")
        # Still track view event for cached results
        if current_user:
            await analytics_service.track_event(
                user_id=current_user.id,
                event_type="prompt_viewed",
                prompt_id=prompt_id,
                metadata={
                    "category": cached_result.get("category"),
                    "from_cache": True
                }
            )
        return PromptResponse(**cached_result)
    
    logger.debug(f"Cache miss for prompt {prompt_id}")
    
    prompt = db.query(Prompt).join(User).filter(
        Prompt.id == prompt_id,
        Prompt.is_active == True
    ).first()
    
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")
    
    # Track view event
    if current_user:
        await analytics_service.track_event(
            user_id=current_user.id,
            event_type="prompt_viewed",
            prompt_id=prompt.id,
            metadata={"category": prompt.category}
        )
    
    response = PromptResponse(
        **prompt.to_dict(),
        seller_name=prompt.seller.full_name or prompt.seller.email,
        seller_company=prompt.seller.company_name
    )
    
    # Cache the result with 30-minute TTL
    cache_data = response.model_dump()
    safe_cache_set(cache_key, cache_data, ttl=settings.cache_prompt_ttl)
    logger.debug(f"Cached prompt detail: {cache_key}")
    
    return response


@router.put("/{prompt_id}", response_model=PromptResponse)
async def update_prompt(
    prompt_id: int,
    prompt_update: PromptUpdate,
    current_user: User = Depends(require_role(["seller", "admin"])),
    db: Session = Depends(get_db)
):
    """Update a prompt (owner or admin only)"""
    prompt = db.query(Prompt).filter(Prompt.id == prompt_id).first()
    
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")
    
    # Check ownership
    if current_user.role != "admin" and prompt.seller_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to update this prompt")
    
    # Update fields
    update_data = prompt_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(prompt, field, value)
    
    db.commit()
    db.refresh(prompt)
    
    # Invalidate cache for this prompt and all prompt lists
    # Invalidate specific prompt cache
    prompt_cache_key = cache.generate_key("prompt:detail", prompt_id=prompt_id)
    safe_cache_delete(prompt_cache_key)
    
    # Invalidate download cache for this prompt
    safe_cache_clear_pattern(f"prompt:download:{prompt_id}*")
    
    # Invalidate all prompt list caches by pattern
    safe_cache_clear_pattern("prompts:list*")
    logger.debug(f"Invalidated cache for updated prompt {prompt_id}")
    
    # Track analytics
    await analytics_service.track_event(
        user_id=current_user.id,
        event_type="prompt_updated",
        prompt_id=prompt.id,
        metadata={"fields_updated": list(update_data.keys())}
    )
    
    return PromptResponse(
        **prompt.to_dict(),
        seller_name=prompt.seller.full_name or prompt.seller.email,
        seller_company=prompt.seller.company_name
    )


@router.delete("/{prompt_id}")
async def delete_prompt(
    prompt_id: int,
    current_user: User = Depends(require_role(["seller", "admin"])),
    db: Session = Depends(get_db)
):
    """Soft delete a prompt (owner or admin only)"""
    prompt = db.query(Prompt).filter(Prompt.id == prompt_id).first()
    
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")
    
    # Check ownership
    if current_user.role != "admin" and prompt.seller_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to delete this prompt")
    
    # Soft delete
    prompt.is_active = False
    db.commit()
    
    # Invalidate cache for this prompt and all prompt lists
    # Invalidate specific prompt cache
    prompt_cache_key = cache.generate_key("prompt:detail", prompt_id=prompt_id)
    safe_cache_delete(prompt_cache_key)
    
    # Invalidate download cache for this prompt
    safe_cache_clear_pattern(f"prompt:download:{prompt_id}*")
    
    # Invalidate all prompt list caches by pattern
    safe_cache_clear_pattern("prompts:list*")
    logger.debug(f"Invalidated cache for deleted prompt {prompt_id}")
    
    # Track analytics
    await analytics_service.track_event(
        user_id=current_user.id,
        event_type="prompt_deleted",
        prompt_id=prompt.id
    )
    
    return {"message": "Prompt deleted successfully"}


@router.post("/{prompt_id}/purchase", response_model=PromptPurchaseResponse)
async def purchase_prompt(
    prompt_id: int,
    purchase_request: PromptPurchaseRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Purchase a prompt"""
    # Get the prompt
    prompt = db.query(Prompt).filter(
        Prompt.id == prompt_id,
        Prompt.is_active == True
    ).first()
    
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")
    
    # Check if already purchased
    existing_purchase = db.query(Transaction).filter(
        Transaction.buyer_id == current_user.id,
        Transaction.prompt_id == prompt_id,
        Transaction.status == "completed"
    ).first()
    
    if existing_purchase:
        raise HTTPException(status_code=400, detail="Prompt already purchased")
    
    try:
        # Create payment intent with Stripe
        payment_intent = await stripe_client.create_payment_intent(
            amount=prompt.price,
            customer_id=current_user.stripe_customer_id,
            metadata={
                "prompt_id": str(prompt_id),
                "buyer_id": str(current_user.id),
                "seller_id": str(prompt.seller_id)
            },
            payment_method_id=purchase_request.payment_method_id
        )
        
        # Create transaction record
        transaction = Transaction(
            buyer_id=current_user.id,
            seller_id=prompt.seller_id,
            prompt_id=prompt_id,
            amount=prompt.price,
            stripe_payment_intent_id=payment_intent["id"],
            status="pending"
        )
        
        db.add(transaction)
        db.commit()
        
        # If payment successful, mark as completed
        if payment_intent["status"] == "succeeded":
            transaction.status = "completed"
            
            # Update prompt stats
            prompt.total_sales += 1
            
            db.commit()
            
            # Track analytics
            await analytics_service.track_event(
                user_id=current_user.id,
                event_type="prompt_purchased",
                prompt_id=prompt_id,
                metadata={
                    "amount": float(prompt.price),
                    "seller_id": prompt.seller_id
                }
            )
        
        return PromptPurchaseResponse(
            transaction_id=transaction.id,
            prompt_id=prompt_id,
            amount=transaction.amount,
            status=transaction.status,
            download_url=f"/api/v1/prompts/{prompt_id}/download",
            receipt_url=payment_intent.get("receipt_url"),
            created_at=transaction.created_at
        )
        
    except Exception as e:
        logger.error(f"Error processing payment: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Payment processing failed")


@router.get("/{prompt_id}/download")
async def download_prompt(
    prompt_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Download a purchased prompt"""
    # Verify purchase
    transaction = db.query(Transaction).filter(
        Transaction.buyer_id == current_user.id,
        Transaction.prompt_id == prompt_id,
        Transaction.status == "completed"
    ).first()
    
    if not transaction:
        raise HTTPException(status_code=403, detail="Prompt not purchased")
    
    # Define a cached function for getting prompt download data
    @cache.cached(
        ttl=settings.cache_prompt_ttl,
        key_prefix=f"prompt:download:{prompt_id}",
        serialization='json'
    )
    def get_prompt_download_data():
        # Get the prompt
        prompt_data = db.query(Prompt).filter(Prompt.id == prompt_id).first()
        
        if not prompt_data:
            return None
        
        return {
            "prompt_id": prompt_data.id,
            "title": prompt_data.title,
            "template": prompt_data.template,
            "variables": prompt_data.variables,
            "usage_notes": prompt_data.usage_notes,
            "model_type": prompt_data.model_type,
            "performance_metrics": prompt_data.performance_metrics
        }
    
    # Get prompt data (will use cache if available)
    prompt_details = get_prompt_download_data()
    
    if not prompt_details:
        raise HTTPException(status_code=404, detail="Prompt not found")
    
    # Track download
    await analytics_service.track_event(
        user_id=current_user.id,
        event_type="prompt_downloaded",
        prompt_id=prompt_id
    )
    
    return prompt_details


@router.post("/{prompt_id}/test", response_model=PromptTestResponse)
async def test_prompt(
    prompt_id: int,
    test_request: PromptTestRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Test a prompt with sample variables (requires purchase)"""
    # Verify purchase
    transaction = db.query(Transaction).filter(
        Transaction.buyer_id == current_user.id,
        Transaction.prompt_id == prompt_id,
        Transaction.status == "completed"
    ).first()
    
    if not transaction:
        raise HTTPException(status_code=403, detail="Prompt not purchased")
    
    # Get the prompt
    prompt = db.query(Prompt).filter(Prompt.id == prompt_id).first()
    
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")
    
    try:
        # Fill template with variables
        filled_template = prompt.template
        for var_name, var_value in test_request.variables.items():
            filled_template = filled_template.replace(f"{{{var_name}}}", var_value)
        
        # Test with OpenAI
        result = await openai_client.test_prompt(
            prompt=filled_template,
            model=prompt.model_type
        )
        
        # Track test
        await analytics_service.track_event(
            user_id=current_user.id,
            event_type="prompt_tested",
            prompt_id=prompt_id,
            metadata={
                "tokens_used": result["tokens_used"],
                "model": prompt.model_type
            }
        )
        
        return PromptTestResponse(
            prompt_id=prompt_id,
            filled_template=filled_template,
            model_response=result["response"],
            tokens_used=result["tokens_used"],
            response_time_ms=result["response_time_ms"],
            estimated_cost=result["estimated_cost"]
        )
        
    except Exception as e:
        logger.error(f"Error testing prompt: {e}")
        raise HTTPException(status_code=500, detail="Failed to test prompt")


@router.post("/{prompt_id}/rate", response_model=PromptRatingResponse)
async def rate_prompt(
    prompt_id: int,
    rating_request: PromptRatingRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Rate a purchased prompt"""
    # Verify purchase
    transaction = db.query(Transaction).filter(
        Transaction.buyer_id == current_user.id,
        Transaction.prompt_id == prompt_id,
        Transaction.status == "completed"
    ).first()
    
    if not transaction:
        raise HTTPException(status_code=403, detail="Prompt not purchased")
    
    # Get the prompt
    prompt = db.query(Prompt).filter(Prompt.id == prompt_id).first()
    
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")
    
    # Update transaction with rating
    transaction.rating = rating_request.rating
    transaction.review = rating_request.review
    
    # Update prompt statistics
    # Calculate new average rating
    rated_transactions = db.query(Transaction).filter(
        Transaction.prompt_id == prompt_id,
        Transaction.rating.isnot(None)
    ).all()
    
    total_rating = sum(t.rating for t in rated_transactions)
    prompt.rating_count = len(rated_transactions)
    prompt.rating_average = total_rating / prompt.rating_count if prompt.rating_count > 0 else None
    
    db.commit()
    
    # Track analytics
    await analytics_service.track_event(
        user_id=current_user.id,
        event_type="prompt_rated",
        prompt_id=prompt_id,
        metadata={
            "rating": rating_request.rating,
            "has_review": bool(rating_request.review)
        }
    )
    
    return PromptRatingResponse(
        id=transaction.id,
        prompt_id=prompt_id,
        user_id=current_user.id,
        rating=transaction.rating,
        review=transaction.review,
        created_at=transaction.updated_at
    )