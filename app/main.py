"""Application entry point with FastAPI."""
import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import List, Optional
from fastapi import FastAPI, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response, HTMLResponse
from fastapi.staticfiles import StaticFiles
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
from app.linkedin_selenium import get_selenium_linkedin_service
from app.scheduler import get_scheduler
from app.admin_dashboard import get_dashboard_html
from app.chrome_lock import get_chrome_lock
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
    LinkedInCookieAuth,
    MonitoredHandleCreate,
    MonitoredHandleUpdate,
    MonitoredHandleResponse,
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


async def _publish_single_scheduled_post(
    scheduled_post: ScheduledPost,
    db: AsyncSession,
    linkedin: any
) -> tuple[bool, str]:
    """
    Shared function to publish a single scheduled post.
    
    This is the SINGLE SOURCE OF TRUTH for publishing logic.
    Used by both:
    - Scheduled publishing (check_and_publish_posts)
    - Manual "Post Now" button (admin_post_now)
    
    Args:
        scheduled_post: The ScheduledPost to publish
        db: Database session
        linkedin: Already initialized LinkedIn service
        
    Returns:
        (success: bool, message: str)
    """
    from datetime import datetime
    from app.health_monitor import update_last_successful_post, increment_failed_posts
    
    post_id = scheduled_post.post_id
    variant_id = scheduled_post.variant_id
    
    logger.info(
        f"📤 Publishing post {post_id} (scheduled for {scheduled_post.scheduled_for.strftime('%I:%M%p')})"
    )
    
    try:
        # Get the original post with all details
        post_result = await db.execute(
            select(LinkedInPost).where(LinkedInPost.id == post_id)
        )
        post = post_result.scalar_one_or_none()
        
        if not post:
            raise ValueError(f"Post {post_id} not found")
        
        # Get variant
        variant_result = await db.execute(
            select(PostVariant).where(PostVariant.id == variant_id)
        )
        variant = variant_result.scalar_one_or_none()
        
        if not variant:
            raise ValueError(f"Variant {variant_id} not found")
        
        if not variant.variant_content:
            raise ValueError(f"Variant {variant_id} has no content")
        
        # Update post status to POSTING
        post.status = PostStatus.POSTING
        await db.commit()
        
        # Attempt to repost using direct URL approach
        if not post.original_post_url:
            raise ValueError(f"Post {post_id} has no original_post_url")
            
        success = await linkedin.repost_by_url(
            post_url=post.original_post_url,
            variant_text=variant.variant_content
        )
        
        if success:
            # Update scheduled post status
            scheduled_post.status = ScheduledPostStatus.PUBLISHED
            scheduled_post.published_at = datetime.now()
            
            # Update original post status
            post.status = PostStatus.POSTED
            post.posted_at = datetime.now()
            post.error_message = None
            
            # Update variant status
            variant.status = VariantStatus.POSTED
            
            # Update health monitoring
            await update_last_successful_post(db)
            
            await db.commit()
            
            logger.info(f"✅ Published post {post_id} successfully")
            return (True, f"Post published successfully to LinkedIn!")
        else:
            # Repost failed - original post not found
            scheduled_post.retry_count += 1
            scheduled_post.last_error = "Original post not found on LinkedIn"
            
            # Update post status to MISSING
            post.status = PostStatus.MISSING
            post.error_message = f"Could not find original post (attempt {scheduled_post.retry_count})"
            post.retry_count = scheduled_post.retry_count
            
            # Lower priority for next attempt
            post.priority = max(0, post.priority - 20)
            
            # Mark as failed if too many retries
            max_retries = 5
            if scheduled_post.retry_count >= max_retries:
                scheduled_post.status = ScheduledPostStatus.FAILED
                post.status = PostStatus.FAILED
                post.error_message = f"Failed after {max_retries} attempts - original post not found"
                
                await increment_failed_posts(db)
                
                logger.error(
                    f"❌ Post {post_id} failed after {max_retries} retries"
                )
            else:
                # Reschedule for 30 minutes later
                scheduled_post.scheduled_for = datetime.now() + timedelta(minutes=30)
                logger.warning(
                    f"⚠️  Post {post_id} not found (retry {scheduled_post.retry_count}/{max_retries}), "
                    f"rescheduled for {scheduled_post.scheduled_for.strftime('%I:%M%p')}"
                )
            
            await db.commit()
            
            return (False, "Original post not found on LinkedIn. It may have been deleted.")
            
    except Exception as e:
        logger.error(f"❌ Error publishing post {post_id}: {e}")
        
        # Update retry count and error
        scheduled_post.retry_count += 1
        scheduled_post.last_error = str(e)
        
        # Update post status
        post.status = PostStatus.FAILED if scheduled_post.retry_count >= 5 else PostStatus.MISSING
        post.error_message = str(e)
        post.retry_count = scheduled_post.retry_count
        
        max_retries = 5
        if scheduled_post.retry_count >= max_retries:
            scheduled_post.status = ScheduledPostStatus.FAILED
            await increment_failed_posts(db)
        else:
            scheduled_post.scheduled_for = datetime.now() + timedelta(minutes=30)
        
        await db.commit()
        
        return (False, f"Error: {str(e)}")


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
    
    # Acquire Chrome lock for posting
    chrome_lock = get_chrome_lock()
    await chrome_lock.acquire(operation="posting", locked_by="check_and_publish_posts")
    
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
                
                # Use Playwright service for reposting
                settings = get_settings()
                linkedin = get_linkedin_service()
                
                # Import health monitoring
                from app.health_monitor import update_last_successful_post, increment_failed_posts
                
                try:
                    published_count = 0
                    failed_count = 0
                    
                    # Publish each due post using shared function
                    for scheduled_post in due_posts:
                        success, message = await _publish_single_scheduled_post(
                            scheduled_post=scheduled_post,
                            db=db,
                            linkedin=linkedin
                        )
                        
                        if success:
                            published_count += 1
                        else:
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
    finally:
        # Always release the Chrome lock
        chrome_lock.release()


async def scheduled_scrape_and_process(test_handle: Optional[str] = None):
    """
    Scheduled background task to scrape LinkedIn posts and process them.
    
    This function runs at 11am and 4pm MST/MDT and:
    1. Scrapes posts from all monitored handles (from database)
    2. Generates AI variants for each post
    3. Sends approval emails to the user
    
    Args:
        test_handle: Optional handle to scrape only (for testing). If provided, only this handle will be scraped.
    """
    operation_name = f"test_scrape_{test_handle}" if test_handle else "scheduled_scrape_and_process"
    log_operation_start(logger, operation_name)
    
    settings = get_settings()
    
    # Get database session to fetch monitored handles
    async for db in get_db():
        # Fetch active monitored handles from database
        from app.models import MonitoredHandle
        
        if test_handle:
            # Test mode: fetch only the specific handle
            result = await db.execute(
                select(MonitoredHandle).where(
                    MonitoredHandle.handle == test_handle,
                    MonitoredHandle.is_active == True
                )
            )
            monitored_handles = result.scalars().all()
            if not monitored_handles:
                logger.error(f"❌ Test handle '{test_handle}' not found or not active")
                return
            logger.info(f"🧪 TEST MODE: Scraping only @{test_handle}")
        else:
            # Normal mode: fetch all active handles
            result = await db.execute(
                select(MonitoredHandle).where(MonitoredHandle.is_active == True)
            )
            monitored_handles = result.scalars().all()
            if not monitored_handles:
                logger.warning("⚠️  No active monitored handles found in database")
                return
            logger.info(f"🔍 Starting scheduled scrape for {len(monitored_handles)} handles")
        
        break  # Just need the first session
    
    # Import health monitoring
    from app.health_monitor import update_last_successful_scrape
    
    total_scraped = 0
    total_processed = 0
    total_failed = 0
    
    # Acquire Chrome lock for scraping
    chrome_lock = get_chrome_lock()
    await chrome_lock.acquire(operation="scraping", locked_by="scheduled_scrape_and_process")
    
    try:
        # Get database session
        async for db in get_db():
            try:
                # Get services (using Playwright for better stability)
                linkedin = get_linkedin_service()
                ai_service = get_ai_service()
                email_service = get_email_service()
                
                # Start browser once for all handles
                await linkedin.start()
                
                try:
                    # Scrape each monitored handle
                    for idx, monitored_handle in enumerate(monitored_handles):
                        handle = monitored_handle.handle
                        display_name = monitored_handle.display_name or "Unknown"
                        relationship = monitored_handle.relationship
                        custom_context = monitored_handle.custom_context
                        
                        # Update progress
                        chrome_lock.update_progress(f"Scraping @{handle} ({idx + 1}/{len(monitored_handles)})")
                        
                        logger.info(f"📥 Scraping @{handle} ({display_name}, {relationship.value})...")
                        
                        try:
                            # Scrape posts from this handle
                            posts = await linkedin.scrape_user_posts(
                                handle=handle,
                                max_posts=10,  # Check last 10 posts
                                days_back=7,   # Within last 7 days
                                author_name=display_name  # Use display name from database
                            )
                            
                            logger.info(f"✅ Scraped {len(posts)} posts from @{handle}")
                            total_scraped += len(posts)
                            
                            # Update last_scraped_at timestamp
                            from datetime import datetime
                            monitored_handle.last_scraped_at = datetime.utcnow()
                            await db.commit()
                            
                            # Update health monitoring
                            await update_last_successful_scrape(db)
                            
                            # Process each scraped post
                            for post_data in posts:
                                try:
                                    # Check if we already have this post (fuzzy match on content + author)
                                    from app.utils import fuzzy_match
                                    
                                    existing_posts = await db.execute(
                                        select(LinkedInPost).where(
                                            LinkedInPost.author_handle == handle
                                        )
                                    )
                                    existing = existing_posts.scalars().all()
                                    
                                    # Check for duplicate using fuzzy matching
                                    is_duplicate = False
                                    for existing_post in existing:
                                        if fuzzy_match(existing_post.original_content, post_data.content, threshold=0.90):
                                            logger.info(f"⏭️  Skipping duplicate post from @{handle}")
                                            is_duplicate = True
                                            break
                                    
                                    if is_duplicate:
                                        continue
                                    
                                    # Create new post in database
                                    new_post = LinkedInPost(
                                        original_post_url=post_data.url,
                                        author_handle=handle,
                                        author_name=post_data.author_name,
                                        original_content=post_data.content,
                                        original_post_date=post_data.post_date,
                                        status=PostStatus.SCRAPED,
                                        scraped_at=datetime.utcnow()
                                    )
                                    db.add(new_post)
                                    await db.flush()  # Get the ID
                                    
                                    logger.info(f"💾 Saved post {new_post.id} from @{handle}")
                                    
                                    # Generate AI variants
                                    logger.info(f"🤖 Generating AI variants for post {new_post.id}...")
                                    variant_texts = await ai_service.generate_variants(
                                        original_content=post_data.content,
                                        author_name=post_data.author_name,
                                        num_variants=3,
                                        relationship=relationship.value,
                                        custom_context=custom_context
                                    )
                                    
                                    # Save variants to database
                                    variants = []
                                    for i, variant_text in enumerate(variant_texts, 1):
                                        variant = PostVariant(
                                            original_post_id=new_post.id,
                                            variant_number=i,
                                            variant_content=variant_text,
                                            ai_model=settings.ai_model,
                                            status=VariantStatus.PENDING
                                        )
                                        db.add(variant)
                                        variants.append(variant)
                                    
                                    await db.flush()
                                    
                                    # Update post status
                                    new_post.status = PostStatus.VARIANTS_GENERATED
                                    new_post.variants_generated_at = datetime.utcnow()
                                    
                                    logger.info(f"✅ Generated {len(variants)} variants for post {new_post.id}")
                                    
                                    # Create approval request
                                    approval_token = generate_approval_token()
                                    approval_request = ApprovalRequest(
                                        original_post_id=new_post.id,
                                        approval_token=approval_token,
                                        expires_at=datetime.utcnow() + timedelta(days=7)
                                    )
                                    db.add(approval_request)
                                    await db.flush()
                                    
                                    # Send approval email
                                    logger.info(f"📧 Sending approval email for post {new_post.id}...")
                                    email_response = await email_service.send_approval_email(
                                        post=new_post,
                                        variants=variants,
                                        approval_token=approval_token
                                    )
                                    
                                    # Update post status
                                    new_post.status = PostStatus.AWAITING_APPROVAL
                                    new_post.approval_email_sent_at = datetime.utcnow()
                                    
                                    logger.info(f"✅ Sent approval email for post {new_post.id}")
                                    
                                    await db.commit()
                                    total_processed += 1
                                    
                                except Exception as e:
                                    logger.error(f"❌ Failed to process post from @{handle}: {e}")
                                    await db.rollback()
                                    total_failed += 1
                                    continue
                            
                        except Exception as e:
                            logger.error(f"❌ Failed to scrape @{handle}: {e}")
                            total_failed += 1
                        
                        # Add human-like delay between profiles (except after last one)
                        if idx < len(monitored_handles) - 1:
                            from app.utils import random_profile_delay
                            random_profile_delay()
                
                finally:
                    # Stop browser after all handles
                    await linkedin.stop()
                
                logger.info(f"✅ Scheduled scrape complete:")
                logger.info(f"   📥 Scraped: {total_scraped} posts")
                logger.info(f"   ✅ Processed: {total_processed} posts")
                logger.info(f"   ❌ Failed: {total_failed} posts")
                
                log_operation_success(
                    logger,
                    "scheduled_scrape_and_process",
                    scraped=total_scraped,
                    processed=total_processed,
                    failed=total_failed
                )
                
            finally:
                await db.close()
                break  # Only use first session from generator
                
    except Exception as e:
        log_operation_error(logger, "scheduled_scrape_and_process", e)
    finally:
        # Always release the Chrome lock
        chrome_lock.release()



async def cleanup_stale_schedule():
    """
    Daily cleanup task to remove DEAD posts from the schedule.
    
    Runs at 3 AM MST to clean up posts that are too old to be relevant.
    
    Rules:
    - DEAD (>7 days): Automatically removed
    - STALE (2-7 days): Kept but logged as low value
    - URGENT posts: Never auto-removed regardless of age
    """
    log_operation_start(logger, "cleanup_stale_schedule")
    
    try:
        settings = get_settings()
        dead_threshold_days = settings.dead_post_threshold_days
        stale_threshold_days = settings.stale_post_threshold_days
        
        async for db in get_db():
            try:
                from datetime import datetime, timedelta
                
                # Get all pending scheduled posts
                result = await db.execute(
                    select(ScheduledPost)
                    .where(ScheduledPost.status == ScheduledPostStatus.PENDING)
                    .options(selectinload(ScheduledPost.post))
                )
                scheduled_posts = result.scalars().all()
                
                now = datetime.now()
                dead_cutoff = now - timedelta(days=dead_threshold_days)
                stale_cutoff = now - timedelta(days=stale_threshold_days)
                
                dead_count = 0
                stale_count = 0
                removed_posts = []
                
                for sched_post in scheduled_posts:
                    if not sched_post.post or not sched_post.post.original_post_date:
                        continue
                    
                    post_age = now - sched_post.post.original_post_date
                    age_days = post_age.total_seconds() / 86400
                    
                    # Never remove URGENT posts automatically
                    if sched_post.priority_level == 'URGENT':
                        logger.debug(
                            f"⏩ Skipping URGENT post {sched_post.id} (age: {age_days:.1f}d) - "
                            f"protected from auto-cleanup"
                        )
                        continue
                    
                    # Remove DEAD posts (>7 days)
                    if sched_post.post.original_post_date < dead_cutoff:
                        dead_count += 1
                        removed_posts.append({
                            'id': sched_post.id,
                            'age_days': age_days,
                            'author': sched_post.post.author_name,
                            'priority': sched_post.priority_level or 'UNKNOWN',
                            'reason': 'DEAD'
                        })
                        
                        logger.info(
                            f"💀 Removing DEAD post {sched_post.id}: "
                            f"{sched_post.post.author_name} (age: {age_days:.1f}d, "
                            f"priority: {sched_post.priority_level})"
                        )
                        
                        # Cancel the scheduled post
                        await db.delete(sched_post)
                    
                    # Log STALE posts but keep them
                    elif sched_post.post.original_post_date < stale_cutoff:
                        stale_count += 1
                        logger.debug(
                            f"⚠️  STALE post {sched_post.id}: "
                            f"{sched_post.post.author_name} (age: {age_days:.1f}d, "
                            f"priority: {sched_post.priority_level})"
                        )
                
                await db.commit()
                
                logger.info(
                    f"🧹 Cleanup complete: removed {dead_count} DEAD posts, "
                    f"{stale_count} STALE posts remain"
                )
                
                log_operation_success(
                    logger,
                    "cleanup_stale_schedule",
                    dead_removed=dead_count,
                    stale_count=stale_count,
                    total_checked=len(scheduled_posts)
                )
                
                return {
                    'removed': removed_posts,
                    'dead_count': dead_count,
                    'stale_count': stale_count,
                    'total_checked': len(scheduled_posts)
                }
                
            finally:
                await db.close()
                break
    
    except Exception as e:
        log_operation_error(logger, "cleanup_stale_schedule", e)
        raise


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
        logger.info(f"   Monitored handles: loaded from database")
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
    from apscheduler.triggers.cron import CronTrigger
    import asyncio
    
    scheduler_instance = AsyncIOScheduler(timezone='America/Denver')  # MST/MDT
    
    # Check for posts to publish every 5 minutes
    scheduler_instance.add_job(
        func=lambda: asyncio.create_task(check_and_publish_posts()),
        trigger=IntervalTrigger(minutes=5),
        id='check_publish_queue',
        name='Check publish queue and publish due posts',
        replace_existing=True
    )
    
    # Scrape LinkedIn posts at 5:30am and 1:00pm MST/MDT
    # Note: Using two separate schedules since times have different minutes
    scheduler_instance.add_job(
        func=lambda: asyncio.create_task(scheduled_scrape_and_process()),
        trigger=CronTrigger(hour='5', minute='30', timezone='America/Denver'),
        id='scheduled_scrape_morning',
        name='Scrape LinkedIn posts (morning)',
        replace_existing=True
    )
    scheduler_instance.add_job(
        func=lambda: asyncio.create_task(scheduled_scrape_and_process()),
        trigger=CronTrigger(hour='13', minute='0', timezone='America/Denver'),
        id='scheduled_scrape_afternoon',
        name='Scrape LinkedIn posts (afternoon)',
        replace_existing=True
    )
    
    # Clean up stale posts daily at 3 AM MST
    scheduler_instance.add_job(
        func=lambda: asyncio.create_task(cleanup_stale_schedule()),
        trigger=CronTrigger(hour='3', minute='0', timezone='America/Denver'),
        id='cleanup_stale_schedule',
        name='Clean up DEAD posts from schedule',
        replace_existing=True
    )
    
    scheduler_instance.start()
    logger.info("✅ Background scheduler started")
    logger.info("   📅 Publishing check: Every 5 minutes")
    logger.info("   📅 Scraping schedule: 5:30 AM and 1:00 PM MST/MDT")
    logger.info("   📅 Cleanup schedule: 3:00 AM MST/MDT (removes DEAD posts >7 days)")
    
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

# Mount noVNC static files for web-based VNC access
import os
if os.path.exists("/app/static/novnc"):
    app.mount("/novnc", StaticFiles(directory="/app/static/novnc"), name="novnc")
    logger.info("✅ noVNC static files mounted at /novnc")


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


@app.get("/admin/vnc", response_class=HTMLResponse)
async def vnc_viewer(request: Request):
    """
    Web-based VNC viewer for manual intervention during security challenges.
    
    This endpoint serves a full-screen noVNC viewer that connects to the
    browser automation session, allowing admin to resolve LinkedIn security
    challenges without needing a separate VNC client.
    """
    settings = get_settings()
    
    # Detect if we're behind a reverse proxy or accessing locally
    host = request.headers.get("host", "localhost:8080")
    is_production = not host.startswith("localhost")
    
    # For production (reverse proxy), use path-based WebSocket connection
    # For local, use host:port connection
    if is_production:
        vnc_params = "path=websockify&autoconnect=true&resize=scale&reconnect=true&password="
    else:
        vnc_params = "host=localhost&port=6080&autoconnect=true&resize=scale&reconnect=true&password="
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>LinkedIn Scraper - VNC Access</title>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            body {{
                margin: 0;
                overflow: hidden;
                background: #1a1a1a;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            }}
            #status {{
                position: absolute;
                top: 10px;
                left: 10px;
                background: rgba(0,0,0,0.8);
                color: #fff;
                padding: 10px 15px;
                border-radius: 5px;
                font-size: 14px;
                z-index: 1000;
            }}
            iframe {{
                width: 100vw;
                height: 100vh;
                border: none;
            }}
        </style>
    </head>
    <body>
        <div id="status">🔒 Secure VNC Connection - LinkedIn Scraper</div>
        <iframe src="/novnc/vnc.html?{vnc_params}"></iframe>
    </body>
    </html>
    """
    
    return HTMLResponse(content=html)


@app.get("/admin")
async def admin_root():
    """Redirect /admin to /admin/dashboard."""
    return RedirectResponse(url="/admin/dashboard")


@app.get("/admin/dashboard", response_class=HTMLResponse)
async def admin_dashboard(
    status: Optional[str] = Query(None),
    author: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """
    Admin dashboard for managing posts and variants.
    Shows all posts with ability to approve, regenerate, or reject.
    """
    settings = get_settings()
    
    # Build query
    query = select(LinkedInPost).options(selectinload(LinkedInPost.variants))
    
    # Filter by status (if provided)
    if status:
        query = query.where(LinkedInPost.status == PostStatus(status))
    
    # Filter by author
    if author:
        query = query.where(LinkedInPost.author_handle == author)
    
    # Order by most recent first
    query = query.order_by(LinkedInPost.scraped_at.desc())
    
    # Execute query
    result = await db.execute(query)
    posts = result.scalars().all()
    
    # Get stats
    stats_result = await db.execute(select(func.count()).select_from(LinkedInPost))
    total_posts = stats_result.scalar_one()
    
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
    
    posted_result = await db.execute(
        select(func.count()).select_from(LinkedInPost).where(
            LinkedInPost.status == PostStatus.POSTED
        )
    )
    posted = posted_result.scalar_one()
    
    rejected_result = await db.execute(
        select(func.count()).select_from(LinkedInPost).where(
            LinkedInPost.status == PostStatus.REJECTED
        )
    )
    rejected = rejected_result.scalar_one()
    
    stats = {
        'total_posts': total_posts,
        'awaiting_approval': awaiting_approval,
        'approved': approved,
        'posted': posted,
        'rejected': rejected
    }
    
    # Get unique authors for dropdown
    authors_result = await db.execute(
        select(LinkedInPost.author_name, LinkedInPost.author_handle)
        .distinct()
        .order_by(LinkedInPost.author_name)
    )
    unique_authors = [
        {'name': row[0], 'handle': row[1]} 
        for row in authors_result.all()
    ]
    
    # Get scheduled posts (upcoming posts ordered by scheduled time)
    from app.models import ScheduledPost
    scheduled_result = await db.execute(
        select(ScheduledPost)
        .options(
            selectinload(ScheduledPost.post),
            selectinload(ScheduledPost.variant)
        )
        .where(ScheduledPost.status == ScheduledPostStatus.PENDING)
        .order_by(ScheduledPost.scheduled_for.asc())
    )
    scheduled_posts = scheduled_result.scalars().all()
    
    # Convert scheduled posts to dict
    schedule_data = []
    for sched in scheduled_posts:
        # Skip if post or variant is missing (orphaned record)
        if not sched.post or not sched.variant:
            logger.warning(f"⚠️  Skipping scheduled post {sched.id} with missing post or variant")
            continue
            
        schedule_data.append({
            'id': sched.id,
            'post_id': sched.post_id,
            'author_name': sched.post.author_name,
            'author_handle': sched.post.author_handle,
            'original_content': sched.post.original_content[:100] + '...' if len(sched.post.original_content) > 100 else sched.post.original_content,
            'variant_content': sched.variant.variant_content[:100] + '...' if len(sched.variant.variant_content) > 100 else sched.variant.variant_content,
            'scheduled_for': sched.scheduled_for.strftime('%Y-%m-%d %H:%M'),
            'approved_at': sched.approved_at.strftime('%Y-%m-%d %H:%M'),
            'priority_level': sched.priority_level or 'NORMAL',
            'post_age_hours': sched.post_age_hours
        })
    
    # Convert posts to dict
    posts_data = []
    for post in posts:
        variants_data = []
        for variant in post.variants:
            variants_data.append({
                'id': variant.id,
                'content': variant.variant_content,
                'status': variant.status.value
            })
        
        # Calculate priority level based on post age
        priority_level = None
        if post.original_post_date:
            from datetime import datetime, timezone
            age_hours = (datetime.now(timezone.utc) - post.original_post_date.replace(tzinfo=timezone.utc)).total_seconds() / 3600
            if age_hours <= 24:
                priority_level = "URGENT"
            elif age_hours <= 48:
                priority_level = "GOOD"
            elif age_hours <= 168:  # 7 days
                priority_level = "OK"
            elif age_hours <= 336:  # 14 days
                priority_level = "STALE"
            else:
                priority_level = "DEAD"
        
        # Format post date in local time for display
        if post.original_post_date:
            # Convert UTC to local time for display
            from datetime import timezone
            import time
            utc_date = post.original_post_date.replace(tzinfo=timezone.utc)
            local_date = utc_date.astimezone()
            post_date_str = local_date.strftime('%Y-%m-%d %H:%M')
        else:
            post_date_str = post.scraped_at.strftime('%Y-%m-%d %H:%M')
        
        posts_data.append({
            'id': post.id,
            'author_name': post.author_name,
            'author_handle': post.author_handle,
            'original_content': post.original_content,
            'original_post_url': post.original_post_url,
            'status': post.status.value,
            'post_date': post_date_str,
            'priority_level': priority_level,
            'variants': variants_data
        })
    
    html = get_dashboard_html(posts_data, stats, settings, current_status=status, current_author=author, authors=unique_authors, schedule=schedule_data)
    return HTMLResponse(content=html)


@app.get("/admin/handles")
async def admin_handles_page():
    """Admin page for managing monitored handles."""
    with open("/tmp/handles_admin.html", "r") as f:
        html = f.read()
    return HTMLResponse(content=html)


@app.post("/admin/posts/{post_id}/approve/{variant_id}")
async def admin_approve_variant(
    post_id: int,
    variant_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Approve a specific variant from admin dashboard."""
    log_operation_start(logger, "admin_approve_variant", post_id=post_id, variant_id=variant_id)
    
    # Get the post
    result = await db.execute(
        select(LinkedInPost)
        .options(selectinload(LinkedInPost.variants))
        .where(LinkedInPost.id == post_id)
    )
    post = result.scalar_one_or_none()
    
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    
    # Get the variant
    variant = next((v for v in post.variants if v.id == variant_id), None)
    if not variant:
        raise HTTPException(status_code=404, detail="Variant not found")
    
    # Update post status
    post.status = PostStatus.APPROVED
    post.approved_at = datetime.utcnow()
    
    # Update variant statuses
    for v in post.variants:
        if v.id == variant_id:
            v.status = VariantStatus.APPROVED
        else:
            v.status = VariantStatus.REJECTED
    
    # Use intelligent scheduler to find optimal posting time
    scheduler = get_scheduler()
    scheduled_time = await scheduler.assign_publish_slot(db, post.id, variant_id)
    
    # Automatically scrub schedule to fix any conflicts
    await scrub_schedule_internal(db)
    
    await db.commit()
    
    log_operation_success(logger, "admin_approve_variant", post_id=post_id, variant_id=variant_id)
    
    return {"success": True, "message": "Variant approved", "scheduled_time": scheduled_time.isoformat()}


@app.post("/admin/posts/{post_id}/regenerate")
async def admin_regenerate_variants(
    post_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Regenerate AI variants for a post."""
    log_operation_start(logger, "admin_regenerate_variants", post_id=post_id)
    
    # Get the post
    result = await db.execute(
        select(LinkedInPost)
        .options(selectinload(LinkedInPost.variants))
        .where(LinkedInPost.id == post_id)
    )
    post = result.scalar_one_or_none()
    
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    
    # Delete old variants
    for variant in post.variants:
        await db.delete(variant)
    
    # Generate new variants
    ai_service = get_ai_service()
    
    # Fetch relationship context from monitored handle
    from app.models import MonitoredHandle
    handle_result = await db.execute(
        select(MonitoredHandle).where(MonitoredHandle.handle == post.author_handle)
    )
    monitored_handle = handle_result.scalar_one_or_none()
    
    relationship = monitored_handle.relationship.value if monitored_handle else None
    custom_context = monitored_handle.custom_context if monitored_handle else None
    
    try:
        variants = await ai_service.generate_variants(
            original_content=post.original_content,
            author_name=post.author_name,
            num_variants=3,
            relationship=relationship,
            custom_context=custom_context
        )
        
        # Create new variant records
        settings = get_settings()
        for i, variant_content in enumerate(variants, 1):
            variant = PostVariant(
                original_post_id=post.id,
                variant_number=i,
                variant_content=variant_content,
                status=VariantStatus.PENDING,
                ai_model=settings.ai_model,
                generation_prompt=f"Regenerated via admin dashboard"
            )
            db.add(variant)
        
        # Update post status
        post.status = PostStatus.AWAITING_APPROVAL
        
        await db.commit()
        
        log_operation_success(logger, "admin_regenerate_variants", post_id=post_id, variants_count=len(variants))
        
        return {"success": True, "message": f"Generated {len(variants)} new variants"}
        
    except Exception as e:
        log_operation_error(logger, "admin_regenerate_variants", e, post_id=post_id)
        raise HTTPException(status_code=500, detail=f"Failed to generate variants: {str(e)}")


@app.get("/admin/status")
async def admin_status():
    """
    Get current Chrome operation status for admin dashboard.
    
    Returns:
        - is_locked: Whether Chrome is currently in use
        - operation: Type of operation (scraping, posting, etc.)
        - started_at: When operation started
        - elapsed_seconds: How long operation has been running
        - current_progress: Human-readable progress (e.g., "Processing @handle 3/10")
        - waiters: Number of operations waiting for Chrome lock
    """
    chrome_lock = get_chrome_lock()
    return JSONResponse(content=chrome_lock.get_status_dict())


@app.post("/admin/posts/{post_id}/reject")
async def admin_reject_post(
    post_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Reject all variants for a post."""
    log_operation_start(logger, "admin_reject_post", post_id=post_id)
    
    # Get the post
    result = await db.execute(
        select(LinkedInPost)
        .options(selectinload(LinkedInPost.variants))
        .where(LinkedInPost.id == post_id)
    )
    post = result.scalar_one_or_none()
    
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    
    # Update post and variant statuses
    post.status = PostStatus.REJECTED
    post.rejected_at = datetime.utcnow()
    
    for variant in post.variants:
        variant.status = VariantStatus.REJECTED
    
    await db.commit()
    
    log_operation_success(logger, "admin_reject_post", post_id=post_id)
    
    return {"success": True, "message": "Post rejected"}


@app.delete("/admin/posts/{post_id}")
async def admin_delete_post(
    post_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Permanently delete a post and all its variants."""
    log_operation_start(logger, "admin_delete_post", post_id=post_id)
    
    # Get the post
    result = await db.execute(
        select(LinkedInPost)
        .options(selectinload(LinkedInPost.variants))
        .where(LinkedInPost.id == post_id)
    )
    post = result.scalar_one_or_none()
    
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    
    # Delete variants first (due to foreign key)
    for variant in post.variants:
        await db.delete(variant)
    
    # Delete any scheduled posts
    scheduled_result = await db.execute(
        select(ScheduledPost).where(ScheduledPost.post_id == post_id)
    )
    scheduled_posts = scheduled_result.scalars().all()
    for sched in scheduled_posts:
        await db.delete(sched)
    
    # Delete the post
    await db.delete(post)
    await db.commit()
    
    log_operation_success(logger, "admin_delete_post", post_id=post_id)
    
    return {"success": True, "message": "Post deleted"}


@app.delete("/admin/scheduled/{scheduled_post_id}")
async def admin_delete_scheduled_post(
    scheduled_post_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Remove a post from the schedule."""
    log_operation_start(logger, "admin_delete_scheduled_post", scheduled_post_id=scheduled_post_id)
    
    # Get the scheduled post
    result = await db.execute(
        select(ScheduledPost).where(ScheduledPost.id == scheduled_post_id)
    )
    scheduled_post = result.scalar_one_or_none()
    
    if not scheduled_post:
        raise HTTPException(status_code=404, detail="Scheduled post not found")
    
    # Delete the scheduled post (but keep the original post and variants)
    await db.delete(scheduled_post)
    await db.commit()
    
    log_operation_success(logger, "admin_delete_scheduled_post", scheduled_post_id=scheduled_post_id)
    
    return {"success": True, "message": "Removed from schedule"}


@app.post("/admin/scheduled/{scheduled_post_id}/post-now")
async def admin_post_now(
    scheduled_post_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Manually post a scheduled item immediately to LinkedIn."""
    log_operation_start(logger, "admin_post_now", scheduled_post_id=scheduled_post_id)
    
    # Acquire Chrome lock for posting (will wait if scraping is in progress)
    chrome_lock = get_chrome_lock()
    await chrome_lock.acquire(operation="posting", locked_by=f"admin_post_now({scheduled_post_id})")
    
    try:
        # Get the scheduled post with related data
        result = await db.execute(
            select(ScheduledPost)
            .where(ScheduledPost.id == scheduled_post_id)
            .options(
                selectinload(ScheduledPost.post),
                selectinload(ScheduledPost.variant)
            )
        )
        scheduled_post = result.scalar_one_or_none()
        
        if not scheduled_post:
            raise HTTPException(status_code=404, detail="Scheduled post not found")
        
        if scheduled_post.status != ScheduledPostStatus.PENDING:
            raise HTTPException(
                status_code=400, 
                detail=f"Cannot post - status is {scheduled_post.status.value}"
            )
        
        # Initialize LinkedIn service  
        settings = get_settings()
        linkedin = get_linkedin_service()
        
        try:
            logger.info(f"📤 Manual post: Publishing post {scheduled_post.post_id} immediately")
            
            # Use shared publishing function (SINGLE SOURCE OF TRUTH)
            success, message = await _publish_single_scheduled_post(
                scheduled_post=scheduled_post,
                db=db,
                linkedin=linkedin
            )
            
            if success:
                log_operation_success(logger, "admin_post_now", scheduled_post_id=scheduled_post_id)
                return {
                    "success": True,
                    "message": message
                }
            else:
                # Failed - raise HTTP exception
                raise HTTPException(
                    status_code=404,
                    detail=message
                )
                
        finally:
            await linkedin.stop()
            
    except HTTPException:
        raise
    except Exception as e:
        log_operation_error(logger, "admin_post_now", e)
        raise HTTPException(status_code=500, detail=f"Failed to post: {str(e)}")
    finally:
        # Always release the Chrome lock
        chrome_lock.release()



async def _keep_browser_open(url: str):
    """Background task to keep browser open for manual inspection."""
    logger.info(f"🚀 Background task started for URL: {url}")
    
    from app.linkedin_selenium import LinkedInSeleniumAutomation
    import time
    
    linkedin = LinkedInSeleniumAutomation(headless=False)  # Non-headless for VNC visibility
    
    try:
        # Start browser
        logger.info("⏳ Starting browser...")
        await linkedin.start()
        logger.info("✅ Browser started")
        
        # Navigate to URL
        logger.info(f"🌐 Navigating to: {url}")
        linkedin.driver.get(url)
        
        logger.info(f"✅ Browser opened to: {url}")
        logger.info("🔍 Browser will stay open - close the window when done")
        logger.info("📺 View at: http://localhost:8080/admin/vnc")
        
        # Keep browser open for 10 minutes or until closed
        for i in range(600):  # 10 minutes
            try:
                # Check if browser is still alive
                linkedin.driver.title
                time.sleep(1)
            except Exception as e:
                logger.info(f"🛑 Browser check failed: {e}")
                break
                
    except Exception as e:
        logger.error(f"❌ Error in browser session: {e}", exc_info=True)
    finally:
        try:
            logger.info("🧹 Cleaning up browser...")
            await linkedin.stop()
            logger.info("✅ Browser cleanup complete")
        except Exception as e:
            logger.error(f"❌ Error stopping browser: {e}")


@app.post("/admin/open-browser")
async def admin_open_browser(url: str = "https://www.linkedin.com/feed/"):
    """
    Open browser and navigate to a URL for manual inspection via VNC.
    Browser stays open until user closes the window.
    
    Query params:
    - url: URL to navigate to (default: LinkedIn feed)
    """
    log_operation_start(logger, "admin_open_browser", url=url)
    
    # Run browser in background task
    asyncio.create_task(_keep_browser_open(url))
    
    # Return immediately
    return {
        "success": True,
        "message": f"Browser opening to {url}. Close the browser window when done.",
        "vnc_url": "http://localhost:8080/admin/vnc"
    }


@app.post("/admin/trigger-scrape")
async def admin_trigger_scrape(
    handle: Optional[str] = Query(None, description="Optional: specific handle to scrape (e.g., 'timcool' or 'company/smartchurchsolutions')"),
    db: AsyncSession = Depends(get_db)
):
    """
    Manually trigger a scrape of monitored LinkedIn handles.
    
    Query params:
    - handle: Optional. If provided, only scrapes this specific handle. Otherwise scrapes all active handles.
    """
    log_operation_start(logger, "admin_trigger_scrape", handle=handle or "all")
    
    # Run the scrape in the background so we can return immediately
    asyncio.create_task(scheduled_scrape_and_process(test_handle=handle))
    
    log_operation_success(logger, "admin_trigger_scrape", handle=handle or "all", status="started")
    
    if handle:
        return {
            "success": True,
            "message": f"Scraping started for handle: {handle}",
            "handle": handle
        }
    else:
        return {
            "success": True,
            "message": "Scraping started for all monitored handles"
        }


@app.post("/admin/test-scrape-handle")
async def admin_test_scrape_handle(
    handle: str = Query(..., description="LinkedIn handle to scrape (e.g., 'timcool' or 'company/smartchurchsolutions')"),
    db: AsyncSession = Depends(get_db)
):
    """Test endpoint to scrape a specific handle without processing all handles."""
    log_operation_start(logger, "admin_test_scrape_handle", handle=handle)
    
    from app.models import MonitoredHandle
    
    # Look up the handle in the database
    result = await db.execute(
        select(MonitoredHandle).where(
            MonitoredHandle.handle == handle,
            MonitoredHandle.is_active == True
        )
    )
    monitored_handle = result.scalar_one_or_none()
    
    if not monitored_handle:
        raise HTTPException(status_code=404, detail=f"Handle '{handle}' not found or not active")
    
    # Run scrape in background for just this handle
    async def scrape_single_handle():
        from app.health_monitor import update_last_successful_scrape
        from app.utils import fuzzy_match
        
        chrome_lock = get_chrome_lock()
        await chrome_lock.acquire(operation="test-scraping", locked_by=f"test_scrape_{handle}")
        
        try:
            async for db_session in get_db():
                try:
                    linkedin = get_linkedin_service()
                    await linkedin.start()
                    
                    try:
                        display_name = monitored_handle.display_name or "Unknown"
                        relationship = monitored_handle.relationship
                        custom_context = monitored_handle.custom_context
                        
                        logger.info(f"🧪 TEST: Scraping @{handle} ({display_name})...")
                        
                        posts = await linkedin.scrape_user_posts(
                            handle=handle,
                            max_posts=10,
                            days_back=7,
                            author_name=display_name
                        )
                        
                        logger.info(f"✅ TEST: Scraped {len(posts)} posts from @{handle}")
                        
                        # Update timestamp
                        monitored_handle.last_scraped_at = datetime.utcnow()
                        await db_session.commit()
                        
                        # Process posts (just log, don't save or generate variants)
                        for idx, post_data in enumerate(posts, 1):
                            logger.info(f"📄 Post {idx}/{len(posts)}: {post_data.content[:100]}...")
                        
                        logger.info(f"✅ TEST COMPLETE: Found {len(posts)} posts from @{handle}")
                        
                    finally:
                        await linkedin.stop()
                        
                except Exception as e:
                    logger.error(f"❌ TEST FAILED: {str(e)}", exc_info=True)
                    raise
                finally:
                    break
                    
        finally:
            await chrome_lock.release()
    
    # Start background task
    asyncio.create_task(scrape_single_handle())
    
    log_operation_success(logger, "admin_test_scrape_handle", handle=handle, status="started")
    
    return {
        "success": True,
        "message": f"Test scrape started for handle: {handle}",
        "handle": handle,
        "display_name": monitored_handle.display_name
    }


@app.post("/admin/cleanup-schedule")
async def admin_cleanup_schedule(
    preview: bool = True,
    db: AsyncSession = Depends(get_db)
):
    """
    Clean up DEAD posts from the schedule.
    
    Query params:
    - preview: If true (default), shows what would be removed without actually removing
    """
    log_operation_start(logger, "admin_cleanup_schedule", preview=preview)
    
    try:
        settings = get_settings()
        dead_threshold_days = settings.dead_post_threshold_days
        stale_threshold_days = settings.stale_post_threshold_days
        
        # Get all pending scheduled posts
        result = await db.execute(
            select(ScheduledPost)
            .where(ScheduledPost.status == ScheduledPostStatus.PENDING)
            .options(selectinload(ScheduledPost.post))
        )
        scheduled_posts = result.scalars().all()
        
        now = datetime.now()
        dead_cutoff = now - timedelta(days=dead_threshold_days)
        stale_cutoff = now - timedelta(days=stale_threshold_days)
        
        dead_posts = []
        stale_posts = []
        protected_posts = []
        
        for sched_post in scheduled_posts:
            if not sched_post.post or not sched_post.post.original_post_date:
                continue
            
            post_age = now - sched_post.post.original_post_date
            age_days = post_age.total_seconds() / 86400
            
            post_info = {
                'id': sched_post.id,
                'age_days': round(age_days, 1),
                'author': sched_post.post.author_name,
                'priority': sched_post.priority_level or 'UNKNOWN',
                'scheduled_for': sched_post.scheduled_for.strftime('%Y-%m-%d %H:%M')
            }
            
            # URGENT posts are protected
            if sched_post.priority_level == 'URGENT':
                protected_posts.append(post_info)
                continue
            
            # DEAD posts (>7 days)
            if sched_post.post.original_post_date < dead_cutoff:
                dead_posts.append(post_info)
                if not preview:
                    await db.delete(sched_post)
            
            # STALE posts (2-7 days)
            elif sched_post.post.original_post_date < stale_cutoff:
                stale_posts.append(post_info)
        
        if not preview:
            await db.commit()
        
        log_operation_success(
            logger,
            "admin_cleanup_schedule",
            preview=preview,
            dead_count=len(dead_posts),
            stale_count=len(stale_posts)
        )
        
        return {
            "success": True,
            "preview": preview,
            "message": f"{'Would remove' if preview else 'Removed'} {len(dead_posts)} DEAD posts",
            "dead_posts": dead_posts,
            "stale_posts": stale_posts,
            "protected_posts": protected_posts,
            "thresholds": {
                "dead_days": dead_threshold_days,
                "stale_days": stale_threshold_days
            }
        }
    
    except Exception as e:
        log_operation_error(logger, "admin_cleanup_schedule", e)
        raise HTTPException(status_code=500, detail=str(e))


async def scrub_schedule_internal(db: AsyncSession):
    """
    Internal function to scrub the schedule (called automatically after approvals).
    Fixes conflicts:
    1. Remove duplicate scheduled posts (same post_id)
    2. Reorder by priority (URGENT > GOOD > OK > STALE)
    3. Fix spacing violations (< 90 min between posts)
    4. Respect posting hours and weekends
    """
    from datetime import timedelta, datetime
    from sqlalchemy import delete
    
    # Get all pending scheduled posts
    result = await db.execute(
        select(ScheduledPost)
        .where(ScheduledPost.status == ScheduledPostStatus.PENDING)
        .order_by(ScheduledPost.scheduled_for)
    )
    scheduled_posts = list(result.scalars().all())
    
    if not scheduled_posts:
        return
    
    changes = []
    
    # Step 1: Find and remove duplicates (keep the first one scheduled)
    seen_post_ids = set()
    duplicates_to_delete = []
    
    for post in scheduled_posts:
        if post.post_id in seen_post_ids:
            duplicates_to_delete.append(post.id)
            logger.info(f"Removing duplicate: Post {post.post_id} scheduled for {post.scheduled_for}")
        else:
            seen_post_ids.add(post.post_id)
    
    # Delete duplicates
    if duplicates_to_delete:
        await db.execute(
            delete(ScheduledPost).where(ScheduledPost.id.in_(duplicates_to_delete))
        )
        await db.commit()
        logger.info(f"Deleted {len(duplicates_to_delete)} duplicate scheduled posts")
    
    # Step 2: Re-fetch remaining posts
    result = await db.execute(
        select(ScheduledPost)
        .where(ScheduledPost.status == ScheduledPostStatus.PENDING)
        .order_by(ScheduledPost.scheduled_for)
    )
    scheduled_posts = list(result.scalars().all())
    
    if not scheduled_posts:
        await db.commit()
        return
    
    # Step 3: Sort by priority (URGENT > GOOD > OK > STALE > None)
    priority_order = {'URGENT': 0, 'GOOD': 1, 'OK': 2, 'STALE': 3, None: 4}
    scheduled_posts.sort(key=lambda p: (priority_order.get(p.priority_level, 4), p.scheduled_for))
    
    # Get scheduler settings
    scheduler = get_scheduler()
    min_spacing = scheduler.min_spacing_minutes
    
    # Step 4: Reschedule all posts with proper spacing and priority order
    # Start from the earliest currently scheduled time or now (whichever is later)
    earliest_time = min(p.scheduled_for for p in scheduled_posts)
    start_time = max(earliest_time, datetime.now())
    
    current_time = scheduler._normalize_to_posting_hours(start_time)
    
    for post in scheduled_posts:
        old_time = post.scheduled_for
        
        # Find next valid slot
        iteration = 0
        while iteration < 365:
            iteration += 1
            
            # Skip weekends if configured
            if scheduler.posting_weekdays_only and current_time.weekday() in [5, 6]:
                current_time = scheduler._move_to_next_weekday(current_time)
                continue
            
            # Check if within posting hours
            current_time = scheduler._normalize_to_posting_hours(current_time)
            
            # Valid slot found
            break
        
        # Assign new time
        post.scheduled_for = current_time
        
        if old_time != current_time:
            logger.info(
                f"Reordered {post.priority_level or 'N/A'}: Post {post.post_id} "
                f"moved from {old_time.strftime('%b %d %I:%M %p')} to "
                f"{current_time.strftime('%b %d %I:%M %p')}"
            )
        
        # Move to next slot with minimum spacing
        current_time = current_time + timedelta(minutes=min_spacing)
    
    await db.commit()
    logger.info("Schedule scrubbed automatically")


@app.post("/admin/scrub-schedule")
async def admin_scrub_schedule(db: AsyncSession = Depends(get_db)):
    """Manually scrub the schedule to fix conflicts."""
    log_operation_start(logger, "admin_scrub_schedule")
    
    await scrub_schedule_internal(db)
    
    log_operation_success(logger, "admin_scrub_schedule")
    
    return {
        "success": True,
        "message": "Schedule scrubbed successfully"
    }


@app.post("/admin/regenerate-all-missing")
async def admin_regenerate_all_missing(db: AsyncSession = Depends(get_db)):
    """Regenerate AI variants for all posts that don't have any variants yet."""
    log_operation_start(logger, "admin_regenerate_all_missing")
    
    # Find posts without variants
    result = await db.execute(
        select(LinkedInPost)
        .outerjoin(PostVariant)
        .group_by(LinkedInPost.id)
        .having(func.count(PostVariant.id) == 0)
    )
    posts_without_variants = result.scalars().all()
    
    if not posts_without_variants:
        return {
            "success": True,
            "message": "No posts found without variants",
            "count": 0
        }
    
    logger.info(f"🔄 Regenerating variants for {len(posts_without_variants)} posts...")
    
    # Process in background
    async def generate_missing_variants():
        ai_service = get_ai_service()
        success_count = 0
        failed_count = 0
        
        async for db_session in get_db():
            for post in posts_without_variants:
                try:
                    logger.info(f"🤖 Generating variants for post {post.id} from @{post.author_handle}")
                    
                    # Generate 3 variants
                    variants = await ai_service.generate_variants(
                        original_content=post.original_content,
                        author_name=post.author_name,
                        author_handle=post.author_handle
                    )
                    
                    # Save variants to database
                    for i, variant_text in enumerate(variants, 1):
                        variant = PostVariant(
                            original_post_id=post.id,
                            variant_number=i,
                            variant_content=variant_text,
                            status=VariantStatus.PENDING
                        )
                        db_session.add(variant)
                    
                    # Update post status
                    post.status = PostStatus.AWAITING_APPROVAL
                    await db_session.commit()
                    
                    success_count += 1
                    logger.info(f"✅ Generated {len(variants)} variants for post {post.id}")
                    
                except Exception as e:
                    failed_count += 1
                    logger.error(f"❌ Failed to generate variants for post {post.id}: {e}")
                    await db_session.rollback()
            
            logger.info(f"✅ Batch complete: {success_count} successful, {failed_count} failed")
            break
    
    # Run in background
    asyncio.create_task(generate_missing_variants())
    
    log_operation_success(logger, "admin_regenerate_all_missing", count=len(posts_without_variants))
    
    return {
        "success": True,
        "message": f"Generating variants for {len(posts_without_variants)} posts in background. Check logs for progress.",
        "count": len(posts_without_variants)
    }


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


@app.get("/webhook/approve/{token}")
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
    
    # Update original post status and save approved variant text
    approval_request.original_post.status = PostStatus.APPROVED
    approval_request.original_post.approved_at = datetime.utcnow()
    approval_request.original_post.approved_variant_text = variant.variant_content
    
    log_database_operation(logger, "UPDATE", "linkedin_posts", post_id, 
                          status=PostStatus.APPROVED.value, 
                          approved_variant_text=f"{variant.variant_content[:50]}...")
    
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
    
    # Return a simple HTML confirmation page
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Post Approved</title>
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                display: flex;
                justify-content: center;
                align-items: center;
                min-height: 100vh;
                margin: 0;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            }}
            .container {{
                background: white;
                padding: 3rem;
                border-radius: 1rem;
                box-shadow: 0 20px 60px rgba(0,0,0,0.3);
                text-align: center;
                max-width: 500px;
            }}
            .checkmark {{
                font-size: 4rem;
                color: #10b981;
                margin-bottom: 1rem;
            }}
            h1 {{
                color: #1f2937;
                margin: 0 0 1rem 0;
                font-size: 2rem;
            }}
            p {{
                color: #6b7280;
                line-height: 1.6;
                margin: 0.5rem 0;
            }}
            .schedule-info {{
                background: #f3f4f6;
                padding: 1rem;
                border-radius: 0.5rem;
                margin-top: 1.5rem;
            }}
            .schedule-info strong {{
                color: #667eea;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="checkmark">✓</div>
            <h1>Post Approved!</h1>
            <p>Your selected variant has been approved and scheduled for posting.</p>
            <div class="schedule-info">
                <p><strong>Scheduled for:</strong><br>
                {scheduled_time.strftime('%A, %B %d at %I:%M %p')}</p>
                <p style="margin-top: 0.5rem; font-size: 0.9rem;">
                ({time_str} from now)
                </p>
            </div>
            <p style="margin-top: 1.5rem; font-size: 0.9rem; color: #9ca3af;">
                You can close this window.
            </p>
        </div>
    </body>
    </html>
    """
    
    return Response(
        content=html_content,
        media_type="text/html",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0"
        }
    )


@app.get("/webhook/reject/{token}")
async def reject_webhook(
    token: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Reject a post via webhook link from email.
    
    This endpoint is called when a user clicks the rejection link in the email.
    Returns a simple confirmation page.
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
        logger.warning(f"⚠️  Rejection link already used for post {approval_request.original_post_id}")
        html_content = """
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Already Responded</title>
            <style>
                body {
                    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    min-height: 100vh;
                    margin: 0;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                }
                .container {
                    background: white;
                    padding: 3rem;
                    border-radius: 1rem;
                    box-shadow: 0 20px 60px rgba(0,0,0,0.3);
                    text-align: center;
                    max-width: 500px;
                }
                .icon {
                    font-size: 4rem;
                    margin-bottom: 1rem;
                }
                h1 {
                    color: #1f2937;
                    margin: 0 0 1rem 0;
                    font-size: 2rem;
                }
                p {
                    color: #6b7280;
                    line-height: 1.6;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="icon">ℹ️</div>
                <h1>Already Responded</h1>
                <p>This approval request has already been responded to.</p>
                <p style="margin-top: 1.5rem; font-size: 0.9rem; color: #9ca3af;">
                    You can close this window.
                </p>
            </div>
        </body>
        </html>
        """
        return Response(content=html_content, media_type="text/html")
    
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
    
    # Return a simple HTML confirmation page
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Post Rejected</title>
        <style>
            body {
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                display: flex;
                justify-content: center;
                align-items: center;
                min-height: 100vh;
                margin: 0;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            }
            .container {
                background: white;
                padding: 3rem;
                border-radius: 1rem;
                box-shadow: 0 20px 60px rgba(0,0,0,0.3);
                text-align: center;
                max-width: 500px;
            }
            .checkmark {
                font-size: 4rem;
                color: #ef4444;
                margin-bottom: 1rem;
            }
            h1 {
                color: #1f2937;
                margin: 0 0 1rem 0;
                font-size: 2rem;
            }
            p {
                color: #6b7280;
                line-height: 1.6;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="checkmark">✗</div>
            <h1>Post Rejected</h1>
            <p>This post has been rejected and will not be posted to LinkedIn.</p>
            <p style="margin-top: 1.5rem; font-size: 0.9rem; color: #9ca3af;">
                You can close this window.
            </p>
        </div>
    </body>
    </html>
    """
    
    return Response(
        content=html_content,
        media_type="text/html",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0"
        }
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


@app.post("/test/trigger-scrape")
async def test_trigger_scrape():
    """
    Manually trigger the scheduled scraping workflow.
    
    This is useful for testing without waiting for 11am/4pm.
    Runs the same logic as the scheduled task:
    1. Scrapes all monitored handles
    2. Generates AI variants
    3. Sends approval emails
    """
    log_operation_start(logger, "test_trigger_scrape")
    
    logger.info("🚀 Manually triggering scheduled scrape workflow...")
    
    # Run the scheduled scrape function
    import asyncio
    asyncio.create_task(scheduled_scrape_and_process())
    
    return {
        "success": True,
        "message": "Scheduled scrape triggered manually. Check logs for progress."
    }


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

@app.post("/linkedin/vnc-login")
async def linkedin_vnc_login(wait_time: int = Query(300, ge=60, le=600, description="Seconds to wait for manual login")):
    """
    Open browser via VNC for manual LinkedIn login.
    
    This endpoint:
    1. Opens Chrome browser (visible via VNC on port 5900)
    2. Navigates to LinkedIn login page
    3. Waits for you to manually login
    4. Saves the complete session (all cookies)
    5. Future scraping will use this session
    
    Args:
        wait_time: How long to wait for manual login (60-600 seconds, default 300)
    
    Steps:
    1. Call this endpoint
    2. Connect to VNC (localhost:5900)
    3. Login to LinkedIn in the browser window
    4. Complete any verification challenges
    5. Wait for the timer to finish
    6. Session will be saved automatically
    """
    log_operation_start(logger, "linkedin_vnc_login", wait_time=wait_time)
    
    try:
        logger.info(f"🌐 Starting VNC manual login (waiting {wait_time}s)...")
        
        # Import and run the manual login script
        from app.linkedin_manual_login import manual_login_session
        
        # Get credentials from settings (loaded from Infisical)
        settings = get_settings()
        email = settings.linkedin_email
        password = settings.linkedin_password
        
        if not email or not password:
            raise HTTPException(
                status_code=500,
                detail="LinkedIn credentials not found in settings"
            )
        
        logger.info(f"🔑 Using credentials for: {email}")
        
        # Run in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        from concurrent.futures import ThreadPoolExecutor
        executor = ThreadPoolExecutor(max_workers=1)
        
        await loop.run_in_executor(executor, manual_login_session, wait_time, email, password)
        
        log_operation_success(logger, "linkedin_vnc_login")
        
        return {
            "success": True,
            "message": f"Manual login session saved successfully!",
            "wait_time": wait_time,
            "next_steps": [
                "Session is now saved with all cookies",
                "You can now use the scraping endpoints",
                "Session will be valid for ~30 days"
            ]
        }
        
    except Exception as e:
        log_operation_error(logger, "linkedin_vnc_login", e)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to complete VNC login: {str(e)}"
        )


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
async def linkedin_cookie_auth(auth_request: LinkedInCookieAuth):
    """
    Authenticate with LinkedIn using li_at cookie (Selenium-based).
    
    Alternative to manual setup - provide your li_at cookie directly.
    To get your li_at cookie:
    1. Login to LinkedIn in your browser
    2. Open DevTools (F12) -> Application -> Cookies
    3. Copy the value of the 'li_at' cookie
    
    Args:
        auth_request: Request containing the li_at cookie value
    """
    log_operation_start(logger, "linkedin_cookie_auth")
    
    # Use Playwright implementation
    linkedin = get_linkedin_service()
    
    try:
        logger.info("🔐 Authenticating with li_at cookie (Selenium)...")
        
        result = await linkedin.login_with_cookies(li_at_cookie=auth_request.li_at_cookie)
        
        if result["success"]:
            log_operation_success(logger, "linkedin_cookie_auth")
            
            return {
                "success": True,
                "message": "LinkedIn session established with cookie successfully (Selenium)!",
                "cookies_file": result.get("cookies_file"),
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
    Scrape posts from a LinkedIn user's profile using Selenium.
    
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
    
    # Get credentials for login
    settings = get_settings()
    email = settings.linkedin_email
    password = settings.linkedin_password
    
    # Use Playwright implementation
    linkedin = get_linkedin_service()
    
    try:
        # Scrape posts with configured lookback
        logger.info(f"🔍 Scraping posts from @{handle} (last {days_back} days) with Selenium...")
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
            "session_health": "healthy",  # Always healthy with email/password login
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


@app.post("/linkedin/repost/{post_id}")
async def linkedin_repost(
    post_id: int,
    db: AsyncSession = Depends(get_db),
    max_retries: int = Query(5, description="Maximum retry attempts"),
    fuzzy_threshold: float = Query(0.80, description="Content similarity threshold (0-1)")
):
    """
    Repost an approved LinkedIn post using the native repost button.
    
    This endpoint:
    1. Verifies post is approved and has approved_variant_text
    2. Searches for the original post by author + content (fuzzy match)
    3. Clicks the repost button
    4. Types the approved variant text as commentary
    5. Submits the repost
    6. Updates post status (POSTED, MISSING, or FAILED)
    
    Args:
        post_id: ID of the approved post to repost
        max_retries: Maximum number of retry attempts (default 5)
        fuzzy_threshold: Content similarity threshold for finding post (default 0.80)
    """
    log_operation_start(logger, "linkedin_repost", post_id=post_id)
    
    # Import health monitoring
    from app.health_monitor import update_last_successful_post, increment_failed_posts
    
    # Use Playwright service for reposting
    settings = get_settings()
    linkedin = get_linkedin_service()
    
    try:
        # Get post from database
        result = await db.execute(
            select(LinkedInPost)
            .where(LinkedInPost.id == post_id)
        )
        post = result.scalar_one_or_none()
        
        if not post:
            raise HTTPException(status_code=404, detail=f"Post {post_id} not found")
        
        # Check post is approved
        if post.status not in [PostStatus.APPROVED, PostStatus.QUEUED, PostStatus.MISSING]:
            raise HTTPException(
                status_code=400,
                detail=f"Post {post_id} is not ready for reposting (status: {post.status.value})"
            )
        
        # Check we have approved variant text
        if not post.approved_variant_text:
            raise HTTPException(
                status_code=400,
                detail=f"Post {post_id} has no approved variant text"
            )
        
        # Check retry count
        if post.retry_count >= max_retries:
            post.status = PostStatus.FAILED
            post.error_message = f"Failed after {max_retries} retry attempts"
            await db.commit()
            
            log_operation_error(
                logger,
                "linkedin_repost",
                Exception(f"Max retries ({max_retries}) exceeded")
            )
            
            await increment_failed_posts(db)
            
            raise HTTPException(
                status_code=400,
                detail=f"Post {post_id} exceeded max retries ({max_retries})"
            )
        
        # Update status to POSTING
        post.status = PostStatus.POSTING
        post.retry_count += 1
        await db.commit()
        
        logger.info(f"🔄 Attempting repost (attempt {post.retry_count}/{max_retries})...")
        
        # Attempt to repost
        success = await linkedin.repost_with_variant(
            author_handle=post.author_handle,
            original_content=post.original_content,
            variant_text=post.approved_variant_text,
            fuzzy_threshold=fuzzy_threshold
        )
        
        if success:
            # Update post status to POSTED
            post.status = PostStatus.POSTED
            post.posted_at = datetime.utcnow()
            post.error_message = None
            await db.commit()
            
            # Update health monitoring
            await update_last_successful_post(db)
            
            log_operation_success(logger, "linkedin_repost", post_id=post_id)
            
            return {
                "success": True,
                "message": f"Successfully reposted post {post_id}",
                "post_id": post_id,
                "status": post.status.value,
                "posted_at": post.posted_at,
                "retry_count": post.retry_count
            }
        else:
            # Repost failed - mark as MISSING for retry
            post.status = PostStatus.MISSING
            post.error_message = f"Could not find original post (attempt {post.retry_count}/{max_retries})"
            
            # Lower priority for re-queuing
            post.priority = max(0, post.priority - 20)
            
            await db.commit()
            
            log_operation_error(
                logger,
                "linkedin_repost",
                Exception(f"Post not found (attempt {post.retry_count}/{max_retries})")
            )
            
            return {
                "success": False,
                "message": f"Could not find original post (attempt {post.retry_count}/{max_retries})",
                "post_id": post_id,
                "status": post.status.value,
                "retry_count": post.retry_count,
                "max_retries": max_retries,
                "will_retry": post.retry_count < max_retries
            }
            
    except HTTPException:
        raise
    except Exception as e:
        # Unexpected error - mark as FAILED
        post.status = PostStatus.FAILED
        post.error_message = f"Unexpected error: {str(e)}"
        await db.commit()
        
        await increment_failed_posts(db)
        
        log_operation_error(logger, "linkedin_repost", e)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to repost: {str(e)}"
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


# ============================================================================
# Monitored Handles Management API
# ============================================================================

@app.get("/handles", response_model=List[MonitoredHandleResponse])
async def get_monitored_handles(
    active_only: bool = False,
    db: AsyncSession = Depends(get_db)
):
    """
    Get all monitored LinkedIn handles.
    
    Query params:
    - active_only: If true, only return active handles
    """
    log_operation_start(logger, "get_monitored_handles", active_only=active_only)
    
    try:
        from app.models import MonitoredHandle
        
        query = select(MonitoredHandle).order_by(MonitoredHandle.handle)
        
        if active_only:
            query = query.where(MonitoredHandle.is_active == True)
        
        result = await db.execute(query)
        handles = result.scalars().all()
        
        log_operation_success(logger, "get_monitored_handles", count=len(handles))
        return handles
        
    except Exception as e:
        log_operation_error(logger, "get_monitored_handles", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/handles", response_model=MonitoredHandleResponse)
async def create_monitored_handle(
    handle_data: MonitoredHandleCreate,
    db: AsyncSession = Depends(get_db)
):
    """Create a new monitored handle."""
    log_operation_start(logger, "create_monitored_handle", handle=handle_data.handle)
    
    try:
        from app.models import MonitoredHandle
        
        # Check if handle already exists
        result = await db.execute(
            select(MonitoredHandle).where(MonitoredHandle.handle == handle_data.handle)
        )
        existing = result.scalar_one_or_none()
        
        if existing:
            raise HTTPException(
                status_code=400,
                detail=f"Handle @{handle_data.handle} is already being monitored"
            )
        
        # Create new handle
        new_handle = MonitoredHandle(
            handle=handle_data.handle,
            display_name=handle_data.display_name,
            relationship=handle_data.relationship,
            custom_context=handle_data.custom_context,
            is_active=handle_data.is_active
        )
        
        db.add(new_handle)
        await db.commit()
        await db.refresh(new_handle)
        
        logger.info(f"✅ Created monitored handle: @{handle_data.handle} ({handle_data.relationship})")
        log_operation_success(logger, "create_monitored_handle", handle=handle_data.handle)
        
        return new_handle
        
    except HTTPException:
        raise
    except Exception as e:
        log_operation_error(logger, "create_monitored_handle", e)
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@app.patch("/handles/{handle_id}", response_model=MonitoredHandleResponse)
async def update_monitored_handle(
    handle_id: int,
    handle_data: MonitoredHandleUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update an existing monitored handle."""
    log_operation_start(logger, "update_monitored_handle", handle_id=handle_id)
    
    try:
        from app.models import MonitoredHandle
        
        # Get existing handle
        result = await db.execute(
            select(MonitoredHandle).where(MonitoredHandle.id == handle_id)
        )
        handle = result.scalar_one_or_none()
        
        if not handle:
            raise HTTPException(status_code=404, detail=f"Handle {handle_id} not found")
        
        # Update fields
        if handle_data.display_name is not None:
            handle.display_name = handle_data.display_name
        if handle_data.relationship is not None:
            handle.relationship = handle_data.relationship
        if handle_data.custom_context is not None:
            handle.custom_context = handle_data.custom_context
        if handle_data.is_active is not None:
            handle.is_active = handle_data.is_active
        
        await db.commit()
        await db.refresh(handle)
        
        logger.info(f"✅ Updated monitored handle: @{handle.handle}")
        log_operation_success(logger, "update_monitored_handle", handle_id=handle_id)
        
        return handle
        
    except HTTPException:
        raise
    except Exception as e:
        log_operation_error(logger, "update_monitored_handle", e)
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/handles/{handle_id}")
async def delete_monitored_handle(
    handle_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Delete a monitored handle."""
    log_operation_start(logger, "delete_monitored_handle", handle_id=handle_id)
    
    try:
        from app.models import MonitoredHandle
        
        # Get existing handle
        result = await db.execute(
            select(MonitoredHandle).where(MonitoredHandle.id == handle_id)
        )
        handle = result.scalar_one_or_none()
        
        if not handle:
            raise HTTPException(status_code=404, detail=f"Handle {handle_id} not found")
        
        handle_name = handle.handle
        
        await db.delete(handle)
        await db.commit()
        
        logger.info(f"🗑️  Deleted monitored handle: @{handle_name}")
        log_operation_success(logger, "delete_monitored_handle", handle_id=handle_id)
        
        return {"success": True, "message": f"Handle @{handle_name} deleted"}
        
    except HTTPException:
        raise
    except Exception as e:
        log_operation_error(logger, "delete_monitored_handle", e)
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=settings.app_port,
        reload=False
    )
