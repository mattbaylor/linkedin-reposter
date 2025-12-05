"""SQLAlchemy database models for LinkedIn Reposter."""
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Text, DateTime, Boolean, ForeignKey, Integer, Enum as SQLEnum
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
import enum


class Base(DeclarativeBase):
    """Base class for all database models."""
    pass


class PostStatus(str, enum.Enum):
    """Status of a LinkedIn post."""
    SCRAPED = "scraped"          # Post scraped from LinkedIn
    VARIANTS_GENERATED = "variants_generated"  # AI variants created
    AWAITING_APPROVAL = "awaiting_approval"    # Email sent, waiting for approval
    APPROVED = "approved"         # User approved a variant
    REJECTED = "rejected"         # User rejected all variants
    POSTED = "posted"            # Successfully posted to LinkedIn
    FAILED = "failed"            # Failed to post


class VariantStatus(str, enum.Enum):
    """Status of a post variant."""
    PENDING = "pending"          # Waiting for approval
    APPROVED = "approved"        # User approved this variant
    REJECTED = "rejected"        # User rejected this variant
    POSTED = "posted"           # Successfully posted to LinkedIn


class ScheduledPostStatus(str, enum.Enum):
    """Status of a scheduled post."""
    PENDING = "pending"          # Waiting to be published
    PUBLISHED = "published"      # Successfully published
    FAILED = "failed"           # Failed to publish (can retry)
    CANCELLED = "cancelled"      # User cancelled


class LinkedInPost(Base):
    """Original LinkedIn post scraped from monitored handles."""
    __tablename__ = "linkedin_posts"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    
    # Source information
    original_post_url: Mapped[str] = mapped_column(String(500), unique=True, index=True)
    author_handle: Mapped[str] = mapped_column(String(100), index=True)
    author_name: Mapped[str] = mapped_column(String(200))
    
    # Post content
    original_content: Mapped[str] = mapped_column(Text)
    
    # Metadata
    scraped_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    original_post_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Status tracking
    status: Mapped[PostStatus] = mapped_column(
        SQLEnum(PostStatus),
        default=PostStatus.SCRAPED,
        index=True
    )
    
    # Processing tracking
    variants_generated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    approval_email_sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    posted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Error tracking
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Relationships
    variants: Mapped[list["PostVariant"]] = relationship(
        "PostVariant",
        back_populates="original_post",
        cascade="all, delete-orphan"
    )
    approval_request: Mapped[Optional["ApprovalRequest"]] = relationship(
        "ApprovalRequest",
        back_populates="original_post",
        uselist=False,
        cascade="all, delete-orphan"
    )
    
    def __repr__(self) -> str:
        return f"<LinkedInPost(id={self.id}, author={self.author_handle}, status={self.status.value})>"


class PostVariant(Base):
    """AI-generated variant of a LinkedIn post."""
    __tablename__ = "post_variants"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    
    # Foreign key to original post
    original_post_id: Mapped[int] = mapped_column(ForeignKey("linkedin_posts.id"), index=True)
    
    # Variant details
    variant_number: Mapped[int] = mapped_column(Integer)  # 1, 2, or 3
    variant_content: Mapped[str] = mapped_column(Text)
    
    # Status
    status: Mapped[VariantStatus] = mapped_column(
        SQLEnum(VariantStatus),
        default=VariantStatus.PENDING,
        index=True
    )
    
    # Metadata
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    posted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # AI metadata
    ai_model: Mapped[str] = mapped_column(String(50))  # e.g., "gpt-4o"
    generation_prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Relationships
    original_post: Mapped["LinkedInPost"] = relationship("LinkedInPost", back_populates="variants")
    
    def __repr__(self) -> str:
        return f"<PostVariant(id={self.id}, variant_number={self.variant_number}, status={self.status.value})>"


class ApprovalRequest(Base):
    """Tracks approval requests sent via email."""
    __tablename__ = "approval_requests"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    
    # Foreign key to original post
    original_post_id: Mapped[int] = mapped_column(
        ForeignKey("linkedin_posts.id"),
        unique=True,
        index=True
    )
    
    # Approval token (secure random string for webhook URLs)
    approval_token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    
    # Email tracking
    email_sent_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    email_message_id: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    
    # Response tracking
    responded_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    approved_variant_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("post_variants.id"),
        nullable=True
    )
    
    # Status
    is_approved: Mapped[bool] = mapped_column(Boolean, default=False)
    is_rejected: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Expiration
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Relationships
    original_post: Mapped["LinkedInPost"] = relationship("LinkedInPost", back_populates="approval_request")
    approved_variant: Mapped[Optional["PostVariant"]] = relationship("PostVariant")
    
    def __repr__(self) -> str:
        status = "approved" if self.is_approved else "rejected" if self.is_rejected else "pending"
        return f"<ApprovalRequest(id={self.id}, token={self.approval_token[:8]}..., status={status})>"
    
    @property
    def is_expired(self) -> bool:
        """Check if approval request has expired."""
        if self.expires_at is None:
            return False
        return datetime.utcnow() > self.expires_at
    
    @property
    def is_pending(self) -> bool:
        """Check if approval request is still pending."""
        return not self.is_approved and not self.is_rejected and not self.is_expired


class ScheduledPost(Base):
    """Post scheduled for future publishing with intelligent spacing."""
    __tablename__ = "scheduled_posts"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    
    # Foreign key to original post
    post_id: Mapped[int] = mapped_column(ForeignKey("linkedin_posts.id"), index=True)
    
    # Foreign key to approved variant
    variant_id: Mapped[int] = mapped_column(ForeignKey("post_variants.id"), index=True)
    
    # Scheduling information
    approved_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    scheduled_for: Mapped[datetime] = mapped_column(DateTime, index=True)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Status
    status: Mapped[ScheduledPostStatus] = mapped_column(
        SQLEnum(ScheduledPostStatus),
        default=ScheduledPostStatus.PENDING,
        index=True
    )
    
    # Retry tracking
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Golden hour tracking
    priority_level: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # URGENT, GOOD, OK, STALE
    priority_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)     # 0-100
    post_age_hours: Mapped[Optional[float]] = mapped_column(nullable=True)            # Age when scheduled
    
    # Metadata
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # Relationships
    post: Mapped["LinkedInPost"] = relationship("LinkedInPost")
    variant: Mapped["PostVariant"] = relationship("PostVariant")
    
    def __repr__(self) -> str:
        return f"<ScheduledPost(id={self.id}, post_id={self.post_id}, scheduled_for={self.scheduled_for}, status={self.status.value})>"

