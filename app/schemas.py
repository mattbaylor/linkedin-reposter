"""Pydantic schemas for request/response validation."""
from __future__ import annotations
from datetime import datetime
from typing import Optional, List, TYPE_CHECKING
from pydantic import BaseModel, Field, HttpUrl


# ============================================================================
# Post Variant Schemas
# ============================================================================

class PostVariantBase(BaseModel):
    """Base schema for post variants."""
    variant_number: int = Field(ge=1, le=3, description="Variant number (1-3)")
    variant_content: str = Field(min_length=1, description="AI-generated variant content")


class PostVariantCreate(PostVariantBase):
    """Schema for creating a new post variant."""
    original_post_id: int
    ai_model: str
    generation_prompt: Optional[str] = None


class PostVariantResponse(PostVariantBase):
    """Schema for post variant response."""
    id: int
    original_post_id: int
    status: str
    generated_at: datetime
    approved_at: Optional[datetime] = None
    posted_at: Optional[datetime] = None
    ai_model: str
    
    class Config:
        from_attributes = True


# ============================================================================
# LinkedIn Post Schemas
# ============================================================================

class LinkedInPostBase(BaseModel):
    """Base schema for LinkedIn posts."""
    original_post_url: str = Field(description="URL of the original LinkedIn post")
    author_handle: str = Field(description="LinkedIn handle of the post author")
    author_name: str = Field(description="Display name of the post author")
    original_content: str = Field(min_length=1, description="Original post content")


class LinkedInPostCreate(LinkedInPostBase):
    """Schema for creating a new LinkedIn post."""
    original_post_date: Optional[datetime] = None


class LinkedInPostResponse(LinkedInPostBase):
    """Schema for LinkedIn post response."""
    id: int
    scraped_at: datetime
    original_post_date: Optional[datetime] = None
    status: str
    variants_generated_at: Optional[datetime] = None
    approval_email_sent_at: Optional[datetime] = None
    approved_at: Optional[datetime] = None
    posted_at: Optional[datetime] = None
    error_message: Optional[str] = None
    
    # Include variants in response
    variants: List[PostVariantResponse] = []
    
    class Config:
        from_attributes = True


class LinkedInPostDetailResponse(LinkedInPostResponse):
    """Detailed LinkedIn post response with approval request info."""
    approval_request: Optional["ApprovalRequestResponse"] = None
    
    class Config:
        from_attributes = True


# ============================================================================
# Approval Request Schemas
# ============================================================================

class ApprovalRequestBase(BaseModel):
    """Base schema for approval requests."""
    original_post_id: int


class ApprovalRequestCreate(ApprovalRequestBase):
    """Schema for creating a new approval request."""
    approval_token: str
    email_message_id: Optional[str] = None
    expires_at: Optional[datetime] = None


class ApprovalRequestResponse(ApprovalRequestBase):
    """Schema for approval request response."""
    id: int
    approval_token: str
    email_sent_at: datetime
    email_message_id: Optional[str] = None
    responded_at: Optional[datetime] = None
    approved_variant_id: Optional[int] = None
    is_approved: bool
    is_rejected: bool
    expires_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


# ============================================================================
# Webhook Schemas
# ============================================================================

class ApprovalWebhookRequest(BaseModel):
    """Schema for approval webhook request."""
    variant_id: int = Field(description="ID of the variant to approve")


class ApprovalWebhookResponse(BaseModel):
    """Schema for approval webhook response."""
    success: bool
    message: str
    post_id: Optional[int] = None
    variant_id: Optional[int] = None


class RejectionWebhookResponse(BaseModel):
    """Schema for rejection webhook response."""
    success: bool
    message: str
    post_id: Optional[int] = None


# ============================================================================
# List/Query Schemas
# ============================================================================

class PostListQuery(BaseModel):
    """Schema for querying posts list."""
    status: Optional[str] = None
    author_handle: Optional[str] = None
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class PostListResponse(BaseModel):
    """Schema for posts list response."""
    total: int
    limit: int
    offset: int
    posts: List[LinkedInPostResponse]


# ============================================================================
# Health & Status Schemas
# ============================================================================

class HealthResponse(BaseModel):
    """Schema for health check response."""
    status: str = "healthy"
    environment: str
    ai_model: str
    timezone: str
    database_initialized: bool = True


class StatsResponse(BaseModel):
    """Schema for statistics response."""
    total_posts: int
    total_variants: int
    awaiting_approval: int
    approved: int
    rejected: int
    posted: int
    failed: int


# ============================================================================
# Scheduled Post Schemas
# ============================================================================

class ScheduledPostResponse(BaseModel):
    """Schema for scheduled post response."""
    id: int
    post_id: int
    variant_id: int
    approved_at: datetime
    scheduled_for: datetime
    published_at: Optional[datetime] = None
    status: str
    retry_count: int
    last_error: Optional[str] = None
    
    # Embedded post info for convenience
    author_handle: Optional[str] = None
    author_name: Optional[str] = None
    
    class Config:
        from_attributes = True


class ScheduleQueueResponse(BaseModel):
    """Schema for schedule queue response."""
    total_scheduled: int
    pending_count: int
    today_count: int
    this_week_count: int
    next_scheduled: Optional[datetime] = None
    queue: List[ScheduledPostResponse]


# Resolve forward references
LinkedInPostDetailResponse.model_rebuild()

