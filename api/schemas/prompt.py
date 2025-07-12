from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any
from datetime import datetime
from decimal import Decimal


class PromptVariableSchema(BaseModel):
    name: str = Field(..., description="Variable name (e.g., 'company_name')")
    description: str = Field(..., description="Description of what this variable represents")
    example: str = Field(..., description="Example value for this variable")
    required: bool = Field(True, description="Whether this variable is required")


class PromptBase(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    
    title: str = Field(..., min_length=3, max_length=200)
    description: str = Field(..., min_length=10, max_length=1000)
    category: str = Field(..., description="Category like 'sales', 'marketing', 'engineering'")
    subcategory: Optional[str] = Field(None, description="More specific categorization")
    tags: List[str] = Field(default_factory=list, max_items=10)
    template: str = Field(..., min_length=10, max_length=10000)
    variables: List[PromptVariableSchema] = Field(default_factory=list)
    model_type: str = Field(..., description="e.g., 'gpt-4o', 'gpt-3.5-turbo'")
    price: Decimal = Field(..., ge=0, decimal_places=2)
    usage_notes: Optional[str] = Field(None, max_length=2000)
    performance_metrics: Optional[Dict[str, Any]] = Field(default_factory=dict)


class PromptCreate(PromptBase):
    pass


class PromptUpdate(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    
    title: Optional[str] = Field(None, min_length=3, max_length=200)
    description: Optional[str] = Field(None, min_length=10, max_length=1000)
    category: Optional[str] = None
    subcategory: Optional[str] = None
    tags: Optional[List[str]] = Field(None, max_items=10)
    template: Optional[str] = Field(None, min_length=10, max_length=10000)
    variables: Optional[List[PromptVariableSchema]] = None
    model_type: Optional[str] = None
    price: Optional[Decimal] = Field(None, ge=0, decimal_places=2)
    usage_notes: Optional[str] = Field(None, max_length=2000)
    performance_metrics: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None


class PromptResponse(PromptBase):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())
    
    id: int
    seller_id: int
    seller_name: str
    seller_company: str
    is_active: bool
    total_sales: int
    rating_average: Optional[float]
    rating_count: int
    created_at: datetime
    updated_at: datetime


class PromptListResponse(BaseModel):
    prompts: List[PromptResponse]
    total: int
    page: int
    per_page: int
    pages: int


class PromptSearchParams(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    
    query: Optional[str] = Field(None, description="Search in title, description, and tags")
    category: Optional[str] = None
    subcategory: Optional[str] = None
    tags: Optional[List[str]] = Field(None, max_items=5)
    min_price: Optional[Decimal] = Field(None, ge=0)
    max_price: Optional[Decimal] = Field(None, ge=0)
    model_type: Optional[str] = None
    seller_id: Optional[int] = None
    sort_by: Optional[str] = Field("created_at", pattern="^(created_at|price|rating_average|total_sales)$")
    sort_order: Optional[str] = Field("desc", pattern="^(asc|desc)$")
    page: int = Field(1, ge=1)
    per_page: int = Field(20, ge=1, le=100)


class PromptPurchaseRequest(BaseModel):
    prompt_id: int
    payment_method_id: Optional[str] = Field(None, description="Stripe payment method ID")


class PromptPurchaseResponse(BaseModel):
    transaction_id: int
    prompt_id: int
    amount: Decimal
    status: str
    download_url: str
    receipt_url: Optional[str]
    created_at: datetime


class PromptRatingRequest(BaseModel):
    rating: int = Field(..., ge=1, le=5)
    review: Optional[str] = Field(None, max_length=1000)


class PromptRatingResponse(BaseModel):
    id: int
    prompt_id: int
    user_id: int
    rating: int
    review: Optional[str]
    created_at: datetime


class PromptTestRequest(BaseModel):
    prompt_id: int
    variables: Dict[str, str] = Field(..., description="Variable values to test with")


class PromptTestResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    
    prompt_id: int
    filled_template: str
    model_response: str
    tokens_used: int
    response_time_ms: int
    estimated_cost: Decimal