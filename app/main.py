"""Application entry point with FastAPI."""
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import List, Optional
from fastapi import FastAPI, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
import time

from app.config import get_settings
from app.database import init_db, close_db, get_db
from app.models import LinkedInPost, PostVariant, ApprovalRequest, PostStatus, VariantStatus, ScheduledPost, ScheduledPostStatus
from app.email import get_email_service, generate_approval_token
from app.ai import get_ai_service
from app.linkedin import get_linkedin_service
from app.scheduler import get_scheduler
from app.schemas import (
    LinkedInPostResponse,
    LinkedInPostDetailResponse,
    PostListResponse,
    ApprovalWebhookResponse,
    RejectionWebhookResponse,
    HealthResponse,
    StatsResponse,
    ScheduledPostResponse,
    ScheduleQueueResponse,
)
from app.logging_config import (
    setup_logging,
    log_operation_start,
    log_operation_success,
    log_operation_error,
    log_workflow_step,
    log_database_operation
)

# Setup enhanced logging
setup_logging(log_level="INFO", log_file="/app/data/linkedin_reposter.log")
logger = logging.getLogger(__name__)


async def check_and_publish_posts():
    """
    Background task to check for posts that are due for publishing.
    
    This function runs every 5 minutes via APScheduler and:
    1. Finds posts scheduled for now or earlier
    2. Publishes them to LinkedIn
    3. Updates status and handles retries
    """
    from datetime import datetime
    from sqlalchemy import and_
    
    log_operation_start(logger, "check_and_publish_posts")
    
    try:
        # Get database session
        async for db in get_db():
            try:
                # Find posts due for publishing
                now = datetime.now()
                
                result = await db.execute(
                    select(ScheduledPost)
                    .where(
                        and_(
                            ScheduledPost.status == ScheduledPostStatus.PENDING,
                            ScheduledPost.scheduled_for <= now
                        )
                    )
                    .options(
                        selectinload(ScheduledPost.post),
                        selectinload(ScheduledPost.variant)
                    )
                    .order_by(ScheduledPost.scheduled_for)
                )
                
                due_posts = result.scalars().all()
                
                if not due_posts:
                    logger.debug("📭 No posts due for publishing")
                    log_operation_success(logger, "check_and_publish_posts", count=0)
                    return
                
                logger.info(f"📬 Found {len(due_posts)} post(s) due for publishing")
                
                # Publish each due post
                linkedin = get_linkedin_service()
                
                try:
                    await linkedin.start()
                    
                    # Check session health
                    health = linkedin.check_session_health()
                    if health["status"] == "expired":
                        logger.error("❌ LinkedIn session expired - cannot publish posts")
                        return
                    
                    # Login if needed
                    if not linkedin.is_logged_in:
                        login_success = await linkedin.login()
                        if not login_success:
                            logger.error("❌ Failed to login - cannot publish posts")
                            return
                    
                    published_count = 0
                    failed_count = 0
                    
                    for scheduled_post in due_posts:
                        post_id = scheduled_post.post_id
                        variant_id = scheduled_post.variant_id
                        
                        logger.info(
                            f"📤 Publishing post {post_id} (scheduled for {scheduled_post.scheduled_for.strftime('%I:%M%p')})"
                        )
                        
                        try:
                            # Get variant content
                            if not scheduled_post.variant:
                                raise ValueError(f"Variant {variant_id} not found")
                            
                            content = scheduled_post.variant.variant_content
                            
                            # Publish to LinkedIn
                            success = await linkedin.publish_post(content)
                            
                            if success:
                                # Update scheduled post status
                                scheduled_post.status = ScheduledPostStatus.PUBLISHED
                                scheduled_post.published_at = datetime.now()
                                
                                # Update original post status
                                if scheduled_post.post:
                                    scheduled_post.post.status = PostStatus.POSTED
                                    scheduled_post.post.posted_at = datetime.now()
                                
                                published_count += 1
                                logger.info(f"✅ Published post {post_id} successfully")
                            else:
                                # Publishing failed
                                scheduled_post.retry_count += 1
                                scheduled_post.last_error = "LinkedIn publish failed"
                                
                                # Mark as failed if too many retries
                                max_retries = 3
                                if scheduled_post.retry_count >= max_retries:
                                    scheduled_post.status = ScheduledPostStatus.FAILED
                                    if scheduled_post.post:
                                        scheduled_post.post.status = PostStatus.FAILED
                                    logger.error(
                                        f"❌ Post {post_id} failed after {max_retries} retries"
                                    )
                                else:
                                    # Reschedule for 30 minutes later
                                    scheduled_post.scheduled_for = now + timedelta(minutes=30)
                                    logger.warning(
                                        f"⚠️  Post {post_id} failed (retry {scheduled_post.retry_count}/{max_retries}), "
                                        f"rescheduled for {scheduled_post.scheduled_for.strftime('%I:%M%p')}"
                                    )
                                
                                failed_count += 1
                            
                            await db.commit()
                            
                        except Exception as e:
                            logger.error(f"❌ Error publishing post {post_id}: {e}")
                            
                            # Update retry count and error
                            scheduled_post.retry_count += 1
                            scheduled_post.last_error = str(e)
                            
                            max_retries = 3
                            if scheduled_post.retry_count >= max_retries:
                                scheduled_post.status = ScheduledPostStatus.FAILED
                                if scheduled_post.post:
                                    scheduled_post.post.status = PostStatus.FAILED
                            else:
                                scheduled_post.scheduled_for = now + timedelta(minutes=30)
                            
                            await db.commit()
                            failed_count += 1
                    
                    logger.info(
                        f"✅ Publishing complete: {published_count} published, {failed_count} failed"
                    )
                    log_operation_success(
                        logger,
                        "check_and_publish_posts",
                        published=published_count,
                        failed=failed_count
                    )
                    
                finally:
                    await linkedin.stop()
                    
            finally:
                await db.close()
                break  # Only use first session from generator
                
    except Exception as e:
        log_operation_error(logger, "check_and_publish_posts", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    logger.info("🚀 Starting LinkedIn Reposter...")
    
    # Load configuration on startup
    try:
        settings = get_settings()
        logger.info(f"✅ Configuration loaded successfully")
        logger.info(f"   Environment: {settings.infisical_environment}")
        logger.info(f"   AI Model: {settings.ai_model}")
        logger.info(f"   Timezone: {settings.timezone}")
        logger.info(f"   Monitoring handles: {settings.linkedin_handles}")
    except Exception as e:
        logger.error(f"❌ Failed to load configuration: {e}")
        raise
    
    # Initialize database
    try:
        await init_db()
    except Exception as e:
        logger.error(f"❌ Failed to initialize database: {e}")
        raise
    
    # Start background scheduler
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.interval import IntervalTrigger
    import asyncio
    
    scheduler_instance = AsyncIOScheduler()
    
    # Check for posts to publish every 5 minutes
    scheduler_instance.add_job(
        func=lambda: asyncio.create_task(check_and_publish_posts()),
        trigger=IntervalTrigger(minutes=5),
        id='check_publish_queue',
        name='Check publish queue and publish due posts',
        replace_existing=True
    )
    
    scheduler_instance.start()
    logger.info("✅ Background scheduler started (checking every 5 minutes)")
    
    yield
    
    # Cleanup on shutdown
    logger.info("🛑 Shutting down LinkedIn Reposter...")
    scheduler_instance.shutdown()
    logger.info("✅ Background scheduler stopped")
    await close_db()


# Create FastAPI app
app = FastAPI(
    title="LinkedIn Reposter",
    description="Automated LinkedIn post monitoring and reposting service",
    version="0.1.0",
    lifespan=lifespan
)


# Request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all HTTP requests with timing."""
    start_time = time.time()
    
    # Log request
    logger.info(f"🌐 {request.method} {request.url.path}")
    logger.debug(f"   Query params: {dict(request.query_params)}")
    logger.debug(f"   Client: {request.client.host if request.client else 'unknown'}")
    
    # Process request
    try:
        response = await call_next(request)
        duration = time.time() - start_time
        
        # Log response
        logger.info(f"✅ {request.method} {request.url.path} → {response.status_code} ({duration:.2f}s)")
        
        return response
        
    except Exception as e:
        duration = time.time() - start_time
        logger.error(f"❌ {request.method} {request.url.path} → Error ({duration:.2f}s): {e}")
        raise


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "LinkedIn Reposter",
        "version": "0.1.0",
        "status": "running"
    }


@app.get("/health", response_model=HealthResponse)
async def health(db: AsyncSession = Depends(get_db)):
    """Health check endpoint."""
    settings = get_settings()
    
    # Check if database is accessible
    database_initialized = False
    try:
        result = await db.execute(select(func.count()).select_from(LinkedInPost))
        database_initialized = True
    except Exception:
        pass
    
    return HealthResponse(
        status="healthy",
        environment=settings.infisical_environment,
        ai_model=settings.ai_model,
        timezone=settings.timezone,
        database_initialized=database_initialized
    )


@app.get("/stats", response_model=StatsResponse)
async def get_stats(db: AsyncSession = Depends(get_db)):
    """Get statistics about posts and processing."""
    # Count total posts
    total_posts_result = await db.execute(select(func.count()).select_from(LinkedInPost))
    total_posts = total_posts_result.scalar_one()
    
    # Count total variants
    total_variants_result = await db.execute(select(func.count()).select_from(PostVariant))
    total_variants = total_variants_result.scalar_one()
    
    # Count posts by status
    awaiting_result = await db.execute(
        select(func.count()).select_from(LinkedInPost).where(
            LinkedInPost.status == PostStatus.AWAITING_APPROVAL
        )
    )
    awaiting_approval = awaiting_result.scalar_one()
    
    approved_result = await db.execute(
        select(func.count()).select_from(LinkedInPost).where(
            LinkedInPost.status == PostStatus.APPROVED
        )
    )
    approved = approved_result.scalar_one()
    
    rejected_result = await db.execute(
        select(func.count()).select_from(LinkedInPost).where(
            LinkedInPost.status == PostStatus.REJECTED
        )
    )
    rejected = rejected_result.scalar_one()
    
    posted_result = await db.execute(
        select(func.count()).select_from(LinkedInPost).where(
            LinkedInPost.status == PostStatus.POSTED
        )
    )
    posted = posted_result.scalar_one()
    
    failed_result = await db.execute(
        select(func.count()).select_from(LinkedInPost).where(
            LinkedInPost.status == PostStatus.FAILED
        )
    )
    failed = failed_result.scalar_one()
    
    return StatsResponse(
        total_posts=total_posts,
        total_variants=total_variants,
        awaiting_approval=awaiting_approval,
        approved=approved,
        rejected=rejected,
        posted=posted,
        failed=failed
    )


@app.get("/posts", response_model=PostListResponse)
async def list_posts(
    status: Optional[str] = Query(None, description="Filter by post status"),
    author_handle: Optional[str] = Query(None, description="Filter by author handle"),
    limit: int = Query(50, ge=1, le=100, description="Number of posts to return"),
    offset: int = Query(0, ge=0, description="Number of posts to skip"),
    db: AsyncSession = Depends(get_db)
):
    """List all LinkedIn posts with optional filtering."""
    # Build query
    query = select(LinkedInPost).options(
        selectinload(LinkedInPost.variants)
    )
    
    # Apply filters
    if status:
        try:
            status_enum = PostStatus(status)
            query = query.where(LinkedInPost.status == status_enum)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")
    
    if author_handle:
        query = query.where(LinkedInPost.author_handle == author_handle)
    
    # Count total (before pagination)
    count_query = select(func.count()).select_from(LinkedInPost)
    if status:
        count_query = count_query.where(LinkedInPost.status == PostStatus(status))
    if author_handle:
        count_query = count_query.where(LinkedInPost.author_handle == author_handle)
    
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()
    
    # Apply pagination and order
    query = query.order_by(LinkedInPost.scraped_at.desc()).limit(limit).offset(offset)
    
    # Execute query
    result = await db.execute(query)
    posts = result.scalars().all()
    
    return PostListResponse(
        total=total,
        limit=limit,
        offset=offset,
        posts=[LinkedInPostResponse.model_validate(post) for post in posts]
    )


@app.get("/posts/{post_id}", response_model=LinkedInPostDetailResponse)
async def get_post(post_id: int, db: AsyncSession = Depends(get_db)):
    """Get detailed information about a specific post."""
    query = select(LinkedInPost).where(LinkedInPost.id == post_id).options(
        selectinload(LinkedInPost.variants),
        selectinload(LinkedInPost.approval_request)
    )
    
    result = await db.execute(query)
    post = result.scalar_one_or_none()
    
    if not post:
        raise HTTPException(status_code=404, detail=f"Post {post_id} not found")
    
    return LinkedInPostDetailResponse.model_validate(post)


@app.get("/webhook/approve/{token}", response_model=ApprovalWebhookResponse)
async def approve_webhook(
    token: str,
    variant_id: int = Query(..., description="ID of the variant to approve"),
    db: AsyncSession = Depends(get_db)
):
    """
    Approve a post variant via webhook link from email.
    
    This endpoint is called when a user clicks an approval link in the email.
    """
    log_operation_start(logger, "approve_webhook", token=token[:16]+"...", variant_id=variant_id)
    
    # Find approval request by token
    logger.debug(f"🔍 Looking up approval request by token: {token[:16]}...")
    
    query = select(ApprovalRequest).where(
        ApprovalRequest.approval_token == token
    ).options(
        selectinload(ApprovalRequest.original_post).selectinload(LinkedInPost.variants)
    )
    
    result = await db.execute(query)
    approval_request = result.scalar_one_or_none()
    
    if not approval_request:
        logger.warning(f"⚠️  Invalid approval token received: {token[:16]}...")
        raise HTTPException(status_code=404, detail="Invalid approval token")
    
    post_id = approval_request.original_post_id
    logger.info(f"✅ Found approval request for post {post_id}")
    
    # Check if already responded
    if approval_request.is_approved or approval_request.is_rejected:
        status = "approved" if approval_request.is_approved else "rejected"
        logger.warning(f"⚠️  Post {post_id} already {status}")
        return ApprovalWebhookResponse(
            success=False,
            message="This approval request has already been responded to",
            post_id=post_id
        )
    
    # Check if expired
    if approval_request.is_expired:
        logger.warning(f"⚠️  Approval request for post {post_id} has expired")
        raise HTTPException(status_code=410, detail="Approval request has expired")
    
    # Find the variant
    logger.debug(f"🔍 Looking up variant {variant_id} for post {post_id}")
    
    variant_query = select(PostVariant).where(
        PostVariant.id == variant_id,
        PostVariant.original_post_id == approval_request.original_post_id
    )
    variant_result = await db.execute(variant_query)
    variant = variant_result.scalar_one_or_none()
    
    if not variant:
        logger.error(f"❌ Variant {variant_id} not found for post {post_id}")
        raise HTTPException(status_code=404, detail="Variant not found")
    
    logger.info(f"✅ Found variant {variant_id} (option {variant.variant_number})")
    
    # Update approval request
    from datetime import datetime
    
    log_workflow_step(logger, "APPROVING", post_id, variant_id=variant_id)
    
    approval_request.is_approved = True
    approval_request.approved_variant_id = variant_id
    approval_request.responded_at = datetime.utcnow()
    
    log_database_operation(logger, "UPDATE", "approval_requests", approval_request.id, 
                          is_approved=True, variant_id=variant_id)
    
    # Update variant status
    variant.status = VariantStatus.APPROVED
    variant.approved_at = datetime.utcnow()
    
    log_database_operation(logger, "UPDATE", "post_variants", variant.id, 
                          status=VariantStatus.APPROVED.value)
    
    # Update original post status
    approval_request.original_post.status = PostStatus.APPROVED
    approval_request.original_post.approved_at = datetime.utcnow()
    
    log_database_operation(logger, "UPDATE", "linkedin_posts", post_id, 
                          status=PostStatus.APPROVED.value)
    
    # Mark other variants as rejected
    rejected_count = 0
    for other_variant in approval_request.original_post.variants:
        if other_variant.id != variant_id:
            other_variant.status = VariantStatus.REJECTED
            rejected_count += 1
    
    logger.info(f"📝 Marked {rejected_count} other variants as rejected")
    
    await db.commit()
    
    log_workflow_step(logger, "APPROVED", post_id, variant_id=variant_id, variant_number=variant.variant_number)
    logger.info(f"✅ Post {post_id} approved (variant {variant_id}, option {variant.variant_number})")
    
    # Schedule post with intelligent spacing and golden hour optimization
    scheduler = get_scheduler()
    scheduled_time = await scheduler.assign_publish_slot(
        db=db,
        post_id=post_id,
        variant_id=variant_id
    )
    
    # Calculate time until posting
    from datetime import datetime
    time_until = (scheduled_time - datetime.now()).total_seconds() / 60
    if time_until < 60:
        time_str = f"{time_until:.0f} minutes"
    elif time_until < 1440:
        time_str = f"{time_until/60:.1f} hours"
    else:
        time_str = f"{time_until/1440:.1f} days"
    
    logger.info(f"📅 Post scheduled for {scheduled_time.strftime('%A %b %d at %I:%M%p')} ({time_str} from now)")
    
    log_operation_success(logger, "approve_webhook", post_id=post_id, variant_id=variant_id)
    
    return ApprovalWebhookResponse(
        success=True,
        message=f"Post approved and scheduled for {scheduled_time.strftime('%A %b %d at %I:%M%p')} ({time_str} from now)",
        post_id=post_id,
        variant_id=variant_id
    )


@app.get("/webhook/reject/{token}", response_model=RejectionWebhookResponse)
async def reject_webhook(
    token: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Reject a post via webhook link from email.
    
    This endpoint is called when a user clicks the rejection link in the email.
    """
    # Find approval request by token
    query = select(ApprovalRequest).where(
        ApprovalRequest.approval_token == token
    ).options(
        selectinload(ApprovalRequest.original_post).selectinload(LinkedInPost.variants)
    )
    
    result = await db.execute(query)
    approval_request = result.scalar_one_or_none()
    
    if not approval_request:
        raise HTTPException(status_code=404, detail="Invalid approval token")
    
    # Check if already responded
    if approval_request.is_approved or approval_request.is_rejected:
        return RejectionWebhookResponse(
            success=False,
            message="This approval request has already been responded to",
            post_id=approval_request.original_post_id
        )
    
    # Update approval request
    from datetime import datetime
    approval_request.is_rejected = True
    approval_request.responded_at = datetime.utcnow()
    
    # Update original post status
    approval_request.original_post.status = PostStatus.REJECTED
    
    # Mark all variants as rejected
    for variant in approval_request.original_post.variants:
        variant.status = VariantStatus.REJECTED
    
    await db.commit()
    
    logger.info(f"❌ Post {approval_request.original_post_id} rejected")
    
    return RejectionWebhookResponse(
        success=True,
        message="Post rejected successfully. No action will be taken.",
        post_id=approval_request.original_post_id
    )


@app.post("/test/send-approval-email")
async def test_send_approval_email(db: AsyncSession = Depends(get_db)):
    """
    Test endpoint to send approval email for existing test post.
    
    Uses the existing post ID 1 and sends an approval email.
    Useful for testing email templates and Postal integration.
    """
    from datetime import datetime
    from sqlalchemy import select
    
    log_operation_start(logger, "test_send_approval_email")
    
    try:
        # Get existing post with ID 1
        result = await db.execute(
            select(LinkedInPost)
            .where(LinkedInPost.id == 1)
        )
        test_post = result.scalar_one_or_none()
        
        if not test_post:
            raise HTTPException(
                status_code=404,
                detail="Test post not found. Run the test endpoint once to create it."
            )
        
        # Get variants
        result = await db.execute(
            select(PostVariant)
            .where(PostVariant.original_post_id == test_post.id)
            .order_by(PostVariant.variant_number)
        )
        variants = result.scalars().all()
        
        if not variants or len(variants) != 3:
            raise HTTPException(
                status_code=400,
                detail=f"Expected 3 variants, found {len(variants)}"
            )
        
        # Get existing approval request
        result = await db.execute(
            select(ApprovalRequest)
            .where(ApprovalRequest.original_post_id == test_post.id)
        )
        approval_request = result.scalar_one_or_none()
        
        if not approval_request:
            raise HTTPException(
                status_code=404,
                detail="Approval request not found"
            )
        
        approval_token = approval_request.approval_token
        
        log_database_operation(logger, "SELECT", "linkedin_posts", test_post.id)
        
        # Send approval email
        email_service = get_email_service()
        result = await email_service.send_approval_email(
            post=test_post,
            variants=list(variants),
            approval_token=approval_token
        )
        
        # Update post status
        test_post.status = PostStatus.AWAITING_APPROVAL
        test_post.approval_email_sent_at = datetime.utcnow()
        
        # Update approval request with message ID
        if result and 'data' in result and 'message_id' in result['data']:
            approval_request.email_message_id = result['data']['message_id']
        
        await db.commit()
        
        log_operation_success(
            logger, 
            "test_send_approval_email",
            post_id=test_post.id,
            message_id=result.get('data', {}).get('message_id', 'unknown')
        )
        
        # Return approval links for easy testing
        return {
            "success": True,
            "message": "Test approval email sent successfully",
            "post_id": test_post.id,
            "approval_token": approval_token,
            "message_id": result.get('data', {}).get('message_id'),
            "approval_links": {
                "variant_1": f"{get_settings().app_base_url}/webhook/approve/{approval_token}?variant_id={variants[0].id}",
                "variant_2": f"{get_settings().app_base_url}/webhook/approve/{approval_token}?variant_id={variants[1].id}",
                "variant_3": f"{get_settings().app_base_url}/webhook/approve/{approval_token}?variant_id={variants[2].id}",
                "reject": f"{get_settings().app_base_url}/webhook/reject/{approval_token}"
            },
            "test_data": {
                "post_id": test_post.id,
                "variant_ids": [v.id for v in variants],
                "approval_request_id": approval_request.id
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        log_operation_error(logger, "test_send_approval_email", e)
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to send test email: {str(e)}"
        )


@app.post("/test/generate-variants")
async def test_generate_variants():
    """
    Test endpoint to generate post variants using AI.
    
    Uses a sample LinkedIn post to test the AI service.
    """
    log_operation_start(logger, "test_generate_variants")
    
    try:
        sample_post = """Just launched our new product! 🚀

After months of hard work, we're excited to share what we've been building. This is a game-changer for the industry.

Check it out and let me know what you think!

#ProductLaunch #Innovation #Technology"""
        
        ai_service = get_ai_service()
        variants = await ai_service.generate_variants(
            original_content=sample_post,
            author_name="Test User",
            num_variants=3
        )
        
        log_operation_success(
            logger,
            "test_generate_variants",
            variants_count=len(variants)
        )
        
        return {
            "success": True,
            "message": "Variants generated successfully",
            "original_post": sample_post,
            "variants": [
                {
                    "variant_number": i + 1,
                    "content": variant
                }
                for i, variant in enumerate(variants)
            ],
            "model": ai_service.model
        }
        
    except Exception as e:
        log_operation_error(logger, "test_generate_variants", e)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate variants: {str(e)}"
        )


@app.post("/test/linkedin-login")
async def test_linkedin_login():
    """
    Test endpoint to verify LinkedIn login functionality.
    
    Starts browser, logs in, and verifies session.
    """
    log_operation_start(logger, "test_linkedin_login")
    
    linkedin = get_linkedin_service()
    
    try:
        await linkedin.start()
        success = await linkedin.login()
        
        log_operation_success(logger, "test_linkedin_login", logged_in=success)
        
        return {
            "success": success,
            "message": "LinkedIn login successful" if success else "LinkedIn login failed",
            "is_logged_in": linkedin.is_logged_in
        }
        
    except Exception as e:
        log_operation_error(logger, "test_linkedin_login", e)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to login to LinkedIn: {str(e)}"
        )
    finally:
        await linkedin.stop()


@app.post("/test/scrape-posts")
async def test_scrape_posts(handle: str = "timcool", max_posts: int = 5):
    """
    Test endpoint to scrape posts from a LinkedIn user.
    
    Args:
        handle: LinkedIn handle to scrape (default: timcool)
        max_posts: Maximum posts to scrape (default: 5)
    """
    log_operation_start(logger, "test_scrape_posts", handle=handle, max_posts=max_posts)
    
    linkedin = get_linkedin_service()
    
    try:
        await linkedin.start()
        await linkedin.login()
        
        posts = await linkedin.scrape_user_posts(handle=handle, max_posts=max_posts)
        
        log_operation_success(logger, "test_scrape_posts", posts_count=len(posts))
        
        return {
            "success": True,
            "message": f"Scraped {len(posts)} posts from {handle}",
            "handle": handle,
            "posts_count": len(posts),
            "posts": [
                {
                    "author_name": post.author_name,
                    "author_handle": post.author_handle,
                    "content": post.content[:200] + "..." if len(post.content) > 200 else post.content,
                    "url": post.url,
                    "post_date": post.post_date.isoformat(),
                }
                for post in posts
            ]
        }
        
    except Exception as e:
        log_operation_error(logger, "test_scrape_posts", e)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to scrape posts: {str(e)}"
        )
    finally:
        await linkedin.stop()


@app.post("/test/publish-post")
async def test_publish_post():
    """
    Test endpoint to publish a test post to LinkedIn.
    
    WARNING: This will actually post to your LinkedIn account!
    """
    log_operation_start(logger, "test_publish_post")
    
    linkedin = get_linkedin_service()
    
    try:
        test_content = """🎉 Testing LinkedIn automation!

This is an automated test post from our new LinkedIn reposter service. 

If you're seeing this, our automation is working! 🚀

#Testing #Automation #LinkedInAPI"""
        
        await linkedin.start()
        await linkedin.login()
        
        success = await linkedin.publish_post(test_content)
        
        log_operation_success(logger, "test_publish_post", published=success)
        
        return {
            "success": success,
            "message": "Post published successfully!" if success else "Failed to publish post",
            "content": test_content
        }
        
    except Exception as e:
        log_operation_error(logger, "test_publish_post", e)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to publish post: {str(e)}"
        )
    finally:
        await linkedin.stop()


# LinkedIn Session Management Endpoints

@app.post("/linkedin/manual-setup")
async def linkedin_manual_setup():
    """
    Perform one-time manual LinkedIn login to establish trusted session.
    
    Opens browser in non-headless mode for manual login. Complete any
    verification challenges, then session will be saved for future automated use.
    
    This should be run:
    - On first setup
    - When session expires (every ~30 days)
    - When LinkedIn requires re-verification
    """
    log_operation_start(logger, "linkedin_manual_setup")
    
    linkedin = get_linkedin_service()
    
    try:
        logger.info("🌐 Starting manual LinkedIn setup (headful browser)...")
        logger.info("   You will see a browser window open")
        logger.info("   Complete the login manually and any verification challenges")
        
        result = await linkedin.manual_setup()
        
        if result["success"]:
            log_operation_success(
                logger,
                "linkedin_manual_setup",
                session_saved=result.get("session_saved", False)
            )
            
            return {
                "success": True,
                "message": "LinkedIn session established and saved successfully!",
                "session_file": result.get("session_file"),
                "cookies_file": result.get("cookies_file"),
                "next_steps": [
                    "Session is now saved and will be used for all future automated operations",
                    "You can now use the scraping and publishing endpoints",
                    "Session will expire in ~30 days - you'll receive email alerts to refresh"
                ]
            }
        else:
            return {
                "success": False,
                "message": result.get("message", "Failed to complete manual setup"),
                "error": result.get("error")
            }
        
    except Exception as e:
        log_operation_error(logger, "linkedin_manual_setup", e)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to complete manual setup: {str(e)}"
        )


@app.post("/linkedin/cookie-auth")
async def linkedin_cookie_auth(li_at_cookie: str = Query(..., description="LinkedIn li_at cookie value")):
    """
    Authenticate with LinkedIn using li_at cookie.
    
    Alternative to manual setup - provide your li_at cookie directly.
    To get your li_at cookie:
    1. Login to LinkedIn in your browser
    2. Open DevTools (F12) -> Application -> Cookies
    3. Copy the value of the 'li_at' cookie
    
    Args:
        li_at_cookie: The li_at cookie value from your browser
    """
    log_operation_start(logger, "linkedin_cookie_auth")
    
    linkedin = get_linkedin_service()
    
    try:
        logger.info("🔐 Authenticating with li_at cookie...")
        
        result = await linkedin.login_with_cookies(li_at_cookie=li_at_cookie)
        
        if result["success"]:
            log_operation_success(logger, "linkedin_cookie_auth")
            
            return {
                "success": True,
                "message": "LinkedIn session established with cookie successfully!",
                "session_file": result.get("session_file"),
                "next_steps": [
                    "Session is now saved and will be used for all future automated operations",
                    "You can now use the scraping and publishing endpoints"
                ]
            }
        else:
            return {
                "success": False,
                "message": result.get("message", "Failed to authenticate with cookie"),
                "error": result.get("error")
            }
        
    except Exception as e:
        log_operation_error(logger, "linkedin_cookie_auth", e)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to authenticate with cookie: {str(e)}"
        )


@app.get("/linkedin/session-status")
async def linkedin_session_status():
    """
    Check LinkedIn session health and age.
    
    Returns:
        - Session existence
        - Session age (days)
        - Health status (healthy/warning/expired)
        - Whether email alerts were sent
    """
    log_operation_start(logger, "linkedin_session_status")
    
    linkedin = get_linkedin_service()
    
    try:
        # Check if session file exists
        import os
        session_file = linkedin.session_file
        session_exists = os.path.exists(session_file)
        
        if not session_exists:
            return {
                "session_exists": False,
                "message": "No LinkedIn session found. Please run /linkedin/manual-setup or /linkedin/cookie-auth",
                "setup_url": f"{get_settings().app_base_url}/linkedin/manual-setup"
            }
        
        # Get session age
        age_days = linkedin.get_session_age()
        
        # Check session health
        health = linkedin.check_session_health()
        
        # Create appropriate message based on status
        if health["status"] == "healthy":
            message = f"Session is healthy (age: {age_days} days)"
        elif health["status"] == "warning":
            message = f"Session is {age_days} days old and should be refreshed soon"
        elif health["status"] == "expired":
            message = f"Session expired (age: {age_days} days) - please re-authenticate"
        elif health["status"] == "unknown_age":
            message = "Session exists but age cannot be determined"
        else:
            message = "Session status unknown"
        
        log_operation_success(
            logger,
            "linkedin_session_status",
            age_days=age_days,
            status=health["status"]
        )
        
        return {
            "session_exists": True,
            "session_file": session_file,
            "age_days": age_days,
            "health_status": health["status"],
            "message": message,
            "email_sent": health.get("email_sent", False),
            "warnings": health.get("warnings", []),
            "recommendations": health.get("recommendations", [])
        }
        
    except Exception as e:
        log_operation_error(logger, "linkedin_session_status", e)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to check session status: {str(e)}"
        )


@app.post("/linkedin/scrape")
async def linkedin_scrape(
    handle: str = Query(..., description="LinkedIn handle to scrape (e.g., 'timcool')"),
    max_posts: int = Query(10, ge=1, le=50, description="Maximum posts to scrape"),
    days_back: Optional[int] = Query(None, ge=1, le=30, description="Scrape posts from last N days (default: from config)"),
    db: AsyncSession = Depends(get_db)
):
    """
    Scrape posts from a LinkedIn user's profile.
    
    This endpoint:
    1. Checks session health (blocks if expired)
    2. Scrapes recent posts from the specified handle (7-day lookback by default)
    3. Saves new posts to database
    4. Returns scraped posts
    
    Args:
        handle: LinkedIn handle to scrape
        max_posts: Maximum number of posts to scrape (1-50)
        days_back: Scrape posts from last N days (default: from config, typically 7 days)
    """
    settings = get_settings()
    
    # Use configured lookback if not specified
    if days_back is None:
        days_back = settings.scraping_lookback_days
    
    log_operation_start(logger, "linkedin_scrape", handle=handle, max_posts=max_posts, days_back=days_back)
    
    linkedin = get_linkedin_service()
    
    try:
        # Check session health first
        health = linkedin.check_session_health()
        
        if health["status"] == "expired":
            logger.error(f"❌ LinkedIn session expired - cannot scrape")
            raise HTTPException(
                status_code=403,
                detail=f"LinkedIn session expired. Please refresh at {settings.app_base_url}/linkedin/manual-setup"
            )
        
        if health["status"] == "warning":
            logger.warning(f"⚠️  LinkedIn session expiring soon (age: {linkedin.get_session_age()} days)")
        
        # Start LinkedIn service
        await linkedin.start()
        
        # Check if already logged in, otherwise use saved session
        if not linkedin.is_logged_in:
            login_success = await linkedin.login()
            if not login_success:
                raise HTTPException(
                    status_code=401,
                    detail="Failed to login with saved session. Please run /linkedin/manual-setup"
                )
        
        # Scrape posts with configured lookback
        logger.info(f"🔍 Scraping posts from @{handle} (last {days_back} days)...")
        posts = await linkedin.scrape_user_posts(handle=handle, max_posts=max_posts, days_back=days_back)
        
        logger.info(f"✅ Scraped {len(posts)} posts from @{handle}")
        
        # Save new posts to database
        new_posts_count = 0
        for post_data in posts:
            # Check if post already exists by URL
            existing = await db.execute(
                select(LinkedInPost).where(LinkedInPost.original_post_url == post_data.url)
            )
            if existing.scalar_one_or_none():
                logger.debug(f"   Post already exists: {post_data.url}")
                continue
            
            # Create new post
            new_post = LinkedInPost(
                author_name=post_data.author_name,
                author_handle=post_data.author_handle,
                original_content=post_data.content,
                original_post_url=post_data.url,
                original_post_date=post_data.post_date,
                status=PostStatus.SCRAPED
            )
            
            db.add(new_post)
            new_posts_count += 1
            logger.info(f"   ✅ Saved new post: {post_data.url}")
        
        await db.commit()
        
        log_operation_success(
            logger,
            "linkedin_scrape",
            handle=handle,
            scraped=len(posts),
            new_posts=new_posts_count
        )
        
        return {
            "success": True,
            "message": f"Scraped {len(posts)} posts from @{handle} ({new_posts_count} new)",
            "handle": handle,
            "scraped_count": len(posts),
            "new_posts_count": new_posts_count,
            "session_health": health["status"],
            "posts": [
                {
                    "author_name": p.author_name,
                    "author_handle": p.author_handle,
                    "content": p.content[:200] + "..." if len(p.content) > 200 else p.content,
                    "url": p.url,
                    "post_date": p.post_date.isoformat()
                }
                for p in posts
            ]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        log_operation_error(logger, "linkedin_scrape", e)
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to scrape LinkedIn posts: {str(e)}"
        )
    finally:
        await linkedin.stop()


@app.post("/linkedin/publish/{post_id}")
async def linkedin_publish(post_id: int, db: AsyncSession = Depends(get_db)):
    """
    Publish an approved post to LinkedIn.
    
    This endpoint:
    1. Checks session health (blocks if expired)
    2. Verifies post is approved
    3. Publishes the approved variant to LinkedIn
    4. Updates post status
    
    Args:
        post_id: ID of the approved post to publish
    """
    log_operation_start(logger, "linkedin_publish", post_id=post_id)
    
    linkedin = get_linkedin_service()
    
    try:
        # Get post from database
        result = await db.execute(
            select(LinkedInPost)
            .where(LinkedInPost.id == post_id)
            .options(selectinload(LinkedInPost.variants))
        )
        post = result.scalar_one_or_none()
        
        if not post:
            raise HTTPException(status_code=404, detail=f"Post {post_id} not found")
        
        # Check post is approved
        if post.status != PostStatus.APPROVED:
            raise HTTPException(
                status_code=400,
                detail=f"Post {post_id} is not approved (status: {post.status.value})"
            )
        
        # Find approved variant
        approved_variant = None
        for variant in post.variants:
            if variant.status == VariantStatus.APPROVED:
                approved_variant = variant
                break
        
        if not approved_variant:
            raise HTTPException(
                status_code=400,
                detail=f"No approved variant found for post {post_id}"
            )
        
        # Check session health
        health = linkedin.check_session_health()
        
        if health["status"] == "expired":
            logger.error(f"❌ LinkedIn session expired - cannot publish")
            raise HTTPException(
                status_code=403,
                detail=f"LinkedIn session expired. Please refresh at {get_settings().app_base_url}/linkedin/manual-setup"
            )
        
        # Start LinkedIn service
        await linkedin.start()
        
        # Login if needed
        if not linkedin.is_logged_in:
            login_success = await linkedin.login()
            if not login_success:
                raise HTTPException(
                    status_code=401,
                    detail="Failed to login with saved session. Please run /linkedin/manual-setup"
                )
        
        # Publish post
        logger.info(f"📤 Publishing post {post_id} to LinkedIn...")
        logger.info(f"   Variant: #{approved_variant.variant_number}")
        logger.info(f"   Content length: {len(approved_variant.content)} chars")
        
        success = await linkedin.publish_post(approved_variant.content)
        
        if success:
            # Update post status
            from datetime import datetime
            post.status = PostStatus.POSTED
            post.posted_at = datetime.utcnow()
            
            await db.commit()
            
            log_operation_success(logger, "linkedin_publish", post_id=post_id)
            
            return {
                "success": True,
                "message": f"Post {post_id} published successfully to LinkedIn!",
                "post_id": post_id,
                "variant_id": approved_variant.id,
                "variant_number": approved_variant.variant_number,
                "content": approved_variant.content
            }
        else:
            # Mark as failed
            post.status = PostStatus.FAILED
            await db.commit()
            
            raise HTTPException(
                status_code=500,
                detail=f"Failed to publish post {post_id} to LinkedIn"
            )
        
    except HTTPException:
        raise
    except Exception as e:
        log_operation_error(logger, "linkedin_publish", e)
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to publish post: {str(e)}"
        )
    finally:
        await linkedin.stop()


# ============================================================================
# Schedule Management Endpoints
# ============================================================================

@app.get("/schedule/queue", response_model=ScheduleQueueResponse)
async def get_schedule_queue(db: AsyncSession = Depends(get_db)):
    """
    Get the current publishing schedule queue.
    
    Returns all scheduled posts sorted by scheduled time,
    with statistics about the queue.
    """
    log_operation_start(logger, "get_schedule_queue")
    
    try:
        from datetime import datetime, timedelta
        from sqlalchemy import and_
        
        # Get all pending scheduled posts
        pending_query = select(ScheduledPost).where(
            ScheduledPost.status == ScheduledPostStatus.PENDING
        ).options(
            selectinload(ScheduledPost.post),
            selectinload(ScheduledPost.variant)
        ).order_by(ScheduledPost.scheduled_for)
        
        result = await db.execute(pending_query)
        scheduled_posts = result.scalars().all()
        
        # Calculate statistics
        total_scheduled = len(scheduled_posts)
        pending_count = total_scheduled
        
        now = datetime.now()
        today_end = now.replace(hour=23, minute=59, second=59)
        week_end = now + timedelta(days=7)
        
        today_count = sum(1 for sp in scheduled_posts if sp.scheduled_for <= today_end)
        this_week_count = sum(1 for sp in scheduled_posts if sp.scheduled_for <= week_end)
        
        next_scheduled = scheduled_posts[0].scheduled_for if scheduled_posts else None
        
        # Build response
        queue_items = []
        for sp in scheduled_posts:
            queue_items.append(ScheduledPostResponse(
                id=sp.id,
                post_id=sp.post_id,
                variant_id=sp.variant_id,
                approved_at=sp.approved_at,
                scheduled_for=sp.scheduled_for,
                published_at=sp.published_at,
                status=sp.status.value,
                retry_count=sp.retry_count,
                last_error=sp.last_error,
                author_handle=sp.post.author_handle if sp.post else None,
                author_name=sp.post.author_name if sp.post else None
            ))
        
        log_operation_success(
            logger,
            "get_schedule_queue",
            total=total_scheduled,
            today=today_count,
            week=this_week_count
        )
        
        return ScheduleQueueResponse(
            total_scheduled=total_scheduled,
            pending_count=pending_count,
            today_count=today_count,
            this_week_count=this_week_count,
            next_scheduled=next_scheduled,
            queue=queue_items
        )
        
    except Exception as e:
        log_operation_error(logger, "get_schedule_queue", e)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get schedule queue: {str(e)}"
        )


@app.post("/schedule/{schedule_id}/reschedule")
async def reschedule_post(
    schedule_id: int,
    new_time: datetime = Query(..., description="New scheduled time (ISO 8601 format)"),
    db: AsyncSession = Depends(get_db)
):
    """
    Reschedule a post to a different time.
    
    Args:
        schedule_id: ID of the scheduled post
        new_time: New scheduled time (must be in the future)
    """
    log_operation_start(logger, "reschedule_post", schedule_id=schedule_id)
    
    try:
        from datetime import datetime
        
        # Get scheduled post
        result = await db.execute(
            select(ScheduledPost).where(ScheduledPost.id == schedule_id)
        )
        scheduled_post = result.scalar_one_or_none()
        
        if not scheduled_post:
            raise HTTPException(
                status_code=404,
                detail=f"Scheduled post {schedule_id} not found"
            )
        
        # Check if already published
        if scheduled_post.status == ScheduledPostStatus.PUBLISHED:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot reschedule post {schedule_id} - already published"
            )
        
        # Validate new time is in the future
        if new_time <= datetime.now():
            raise HTTPException(
                status_code=400,
                detail="New scheduled time must be in the future"
            )
        
        # Update scheduled time
        old_time = scheduled_post.scheduled_for
        scheduled_post.scheduled_for = new_time
        
        await db.commit()
        
        logger.info(f"📅 Rescheduled post {schedule_id}: {old_time} → {new_time}")
        log_operation_success(logger, "reschedule_post", schedule_id=schedule_id)
        
        return {
            "success": True,
            "message": f"Post rescheduled from {old_time.strftime('%Y-%m-%d %H:%M')} to {new_time.strftime('%Y-%m-%d %H:%M')}",
            "schedule_id": schedule_id,
            "old_time": old_time,
            "new_time": new_time
        }
        
    except HTTPException:
        raise
    except Exception as e:
        log_operation_error(logger, "reschedule_post", e)
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to reschedule post: {str(e)}"
        )


@app.delete("/schedule/{schedule_id}")
async def cancel_scheduled_post(
    schedule_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Cancel a scheduled post.
    
    Args:
        schedule_id: ID of the scheduled post to cancel
    """
    log_operation_start(logger, "cancel_scheduled_post", schedule_id=schedule_id)
    
    try:
        # Get scheduled post
        result = await db.execute(
            select(ScheduledPost).where(ScheduledPost.id == schedule_id)
        )
        scheduled_post = result.scalar_one_or_none()
        
        if not scheduled_post:
            raise HTTPException(
                status_code=404,
                detail=f"Scheduled post {schedule_id} not found"
            )
        
        # Check if already published
        if scheduled_post.status == ScheduledPostStatus.PUBLISHED:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot cancel post {schedule_id} - already published"
            )
        
        # Mark as cancelled
        scheduled_post.status = ScheduledPostStatus.CANCELLED
        
        await db.commit()
        
        logger.info(f"❌ Cancelled scheduled post {schedule_id}")
        log_operation_success(logger, "cancel_scheduled_post", schedule_id=schedule_id)
        
        return {
            "success": True,
            "message": f"Scheduled post {schedule_id} cancelled successfully",
            "schedule_id": schedule_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        log_operation_error(logger, "cancel_scheduled_post", e)
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to cancel scheduled post: {str(e)}"
        )


if __name__ == "__main__":
    import uvicorn
    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=settings.app_port,
        reload=False
    )
