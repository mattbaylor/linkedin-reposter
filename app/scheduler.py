"""Intelligent post scheduling to avoid overwhelming LinkedIn algorithm."""
import logging
import random
from datetime import datetime, timedelta, date
from typing import List, Optional
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import ScheduledPost, ScheduledPostStatus, LinkedInPost, PostVariant
from app.logging_config import log_operation_start, log_operation_success, log_operation_error

logger = logging.getLogger(__name__)


class PostScheduler:
    """Intelligent scheduler for LinkedIn posts with golden hour optimization."""
    
    def __init__(self):
        """Initialize the scheduler with configuration."""
        settings = get_settings()
        
        self.daily_post_limit = settings.daily_post_limit
        self.min_spacing_minutes = settings.min_post_spacing_minutes
        self.posting_hour_start = settings.posting_hour_start
        self.posting_hour_end = settings.posting_hour_end
        self.posting_weekdays_only = settings.posting_weekdays_only
        self.enable_jitter = settings.enable_posting_jitter
        self.jitter_minutes = settings.posting_jitter_minutes
        
        # Golden hour thresholds (in hours since original post)
        self.golden_hour_urgent = 3    # < 3 hours = URGENT (ride the wave!)
        self.golden_hour_good = 12     # < 12 hours = GOOD (still relevant)
        self.golden_hour_ok = 24       # < 24 hours = OK (acceptable)
        self.golden_hour_stale = 48    # > 48 hours = STALE (consider skipping)
        
        logger.info(f"📅 Post Scheduler initialized with Golden Hour optimization")
        logger.info(f"   Daily limit: {self.daily_post_limit} posts")
        logger.info(f"   Min spacing: {self.min_spacing_minutes} minutes")
        logger.info(f"   Posting hours: {self.posting_hour_start}:00 - {self.posting_hour_end}:00")
        logger.info(f"   Weekdays only: {self.posting_weekdays_only}")
        logger.info(f"   Jitter: ±{self.jitter_minutes} min" if self.enable_jitter else "   Jitter: disabled")
        logger.info(f"   Golden hour windows:")
        logger.info(f"      🔥 URGENT: < {self.golden_hour_urgent}h (prioritize ASAP)")
        logger.info(f"      ✅ GOOD: < {self.golden_hour_good}h (schedule soon)")
        logger.info(f"      ⏰ OK: < {self.golden_hour_ok}h (normal scheduling)")
        logger.info(f"      ⚠️  STALE: > {self.golden_hour_stale}h (low priority)")
    
    async def assign_publish_slot(
        self,
        db: AsyncSession,
        post_id: int,
        variant_id: int
    ) -> datetime:
        """
        Intelligently assign a publish time for an approved post.
        
        Algorithm:
        1. Calculate post age and golden hour priority
        2. Get all currently scheduled posts
        3. Find next available time slot based on priority:
           - URGENT (< 3h): Schedule ASAP (next available slot)
           - GOOD (< 12h): Schedule today if possible
           - OK (< 24h): Normal scheduling
           - STALE (> 48h): Low priority (back of queue)
        4. Ensure slot satisfies constraints:
           - Within posting hours (6am-9pm MST)
           - Not on weekend (if weekdays_only=true)
           - Doesn't exceed daily post limit
           - Has minimum spacing from previous post
        5. Add random jitter for natural appearance
        
        Args:
            db: Database session
            post_id: ID of the approved post
            variant_id: ID of the approved variant
            
        Returns:
            datetime: Scheduled publish time
        """
        log_operation_start(logger, "assign_publish_slot", post_id=post_id, variant_id=variant_id)
        
        # Get the original post to calculate age
        result = await db.execute(
            select(LinkedInPost).where(LinkedInPost.id == post_id)
        )
        original_post = result.scalar_one_or_none()
        
        if not original_post:
            raise ValueError(f"Post {post_id} not found")
        
        # Calculate post age and priority
        priority = self._calculate_priority(original_post)
        
        logger.info(
            f"📊 Post age: {priority['age_hours']:.1f}h "
            f"| Priority: {priority['level']} {priority['emoji']}"
        )
        
        # Get all scheduled posts
        scheduled_posts = await self._get_all_scheduled_posts(db)
        logger.info(f"📊 Current queue: {len(scheduled_posts)} posts scheduled")
        
        # Find next available slot based on priority
        if priority['level'] == 'URGENT':
            # URGENT: Schedule ASAP (next available slot, even if it pushes other posts)
            candidate_time = datetime.now()
            logger.info(f"🔥 URGENT post - scheduling ASAP")
        elif priority['level'] == 'GOOD':
            # GOOD: Try to schedule today, otherwise next available
            candidate_time = datetime.now()
            logger.info(f"✅ GOOD timing - trying to schedule today")
        elif priority['level'] == 'STALE':
            # STALE: Back of the queue
            if scheduled_posts:
                last_scheduled = max(post.scheduled_for for post in scheduled_posts)
                candidate_time = last_scheduled + timedelta(minutes=self.min_spacing_minutes)
            else:
                candidate_time = datetime.now()
            logger.info(f"⚠️  STALE post - adding to back of queue")
        else:
            # OK: Normal scheduling
            candidate_time = datetime.now()
            logger.info(f"⏰ Normal scheduling")
        
        # Find valid slot
        iteration = 0
        max_iterations = 365  # Safety limit: don't schedule more than a year out
        
        while iteration < max_iterations:
            iteration += 1
            
            # Normalize to start of posting hours if before/after
            candidate_time = self._normalize_to_posting_hours(candidate_time)
            
            # Skip weekends if configured
            if self.posting_weekdays_only and candidate_time.weekday() in [5, 6]:
                logger.debug(f"   Skipping weekend: {candidate_time.strftime('%A %Y-%m-%d')}")
                candidate_time = self._move_to_next_weekday(candidate_time)
                continue
            
            # Check if this day is at daily limit
            posts_on_day = self._count_posts_on_day(scheduled_posts, candidate_time.date())
            if posts_on_day >= self.daily_post_limit:
                logger.debug(
                    f"   Day {candidate_time.date()} at limit "
                    f"({posts_on_day}/{self.daily_post_limit} posts)"
                )
                candidate_time = self._move_to_next_day(candidate_time)
                continue
            
            # Check spacing from last scheduled post
            last_post_time = self._get_last_scheduled_time_before(scheduled_posts, candidate_time)
            if last_post_time:
                time_diff = (candidate_time - last_post_time).total_seconds() / 60
                if time_diff < self.min_spacing_minutes:
                    # Move forward by remaining spacing needed
                    needed_spacing = self.min_spacing_minutes - time_diff
                    candidate_time = candidate_time + timedelta(minutes=needed_spacing)
                    logger.debug(
                        f"   Spacing violation: need {needed_spacing:.0f} more minutes from last post"
                    )
                    continue
            
            # Found valid slot!
            logger.info(f"✅ Found slot: {candidate_time.strftime('%A %b %d at %I:%M%p')}")
            break
        
        if iteration >= max_iterations:
            logger.warning(f"⚠️  Hit max iterations finding slot - scheduling far in future")
        
        # Add jitter for natural appearance
        if self.enable_jitter:
            jitter = random.randint(-self.jitter_minutes, self.jitter_minutes)
            candidate_time = candidate_time + timedelta(minutes=jitter)
            logger.debug(f"   Applied jitter: {jitter:+d} minutes")
        
        # Create scheduled post entry with priority information
        scheduled_post = ScheduledPost(
            post_id=post_id,
            variant_id=variant_id,
            approved_at=datetime.now(),
            scheduled_for=candidate_time,
            status=ScheduledPostStatus.PENDING,
            priority_level=priority['level'],
            priority_score=priority['priority_score'],
            post_age_hours=priority['age_hours']
        )
        
        db.add(scheduled_post)
        await db.commit()
        await db.refresh(scheduled_post)
        
        # Log with priority context
        time_until = (candidate_time - datetime.now()).total_seconds() / 60
        if time_until < 60:
            time_str = f"{time_until:.0f} minutes"
        elif time_until < 1440:
            time_str = f"{time_until/60:.1f} hours"
        else:
            time_str = f"{time_until/1440:.1f} days"
        
        logger.info(
            f"📅 Scheduled post {post_id} for {candidate_time.strftime('%A %b %d at %I:%M%p')} "
            f"({time_str} from now) | Priority: {priority['emoji']} {priority['level']}"
        )
        
        log_operation_success(
            logger,
            "assign_publish_slot",
            post_id=post_id,
            scheduled_for=candidate_time.isoformat()
        )
        
        return candidate_time
    
    async def _get_all_scheduled_posts(self, db: AsyncSession) -> List[ScheduledPost]:
        """Get all scheduled posts (pending or recently published)."""
        # Get pending posts + posts published in last 7 days (for spacing calculation)
        cutoff = datetime.now() - timedelta(days=7)
        
        result = await db.execute(
            select(ScheduledPost)
            .where(
                and_(
                    ScheduledPost.status.in_([
                        ScheduledPostStatus.PENDING,
                        ScheduledPostStatus.PUBLISHED
                    ]),
                    ScheduledPost.scheduled_for >= cutoff
                )
            )
            .order_by(ScheduledPost.scheduled_for)
        )
        
        return list(result.scalars().all())
    
    def _normalize_to_posting_hours(self, dt: datetime) -> datetime:
        """Move datetime to within posting hours."""
        if dt.hour < self.posting_hour_start:
            # Before posting hours - move to start of posting window
            return dt.replace(hour=self.posting_hour_start, minute=0, second=0, microsecond=0)
        elif dt.hour >= self.posting_hour_end:
            # After posting hours - move to next day's start
            next_day = dt + timedelta(days=1)
            return next_day.replace(
                hour=self.posting_hour_start,
                minute=0,
                second=0,
                microsecond=0
            )
        else:
            # Already within posting hours
            return dt
    
    def _move_to_next_weekday(self, dt: datetime) -> datetime:
        """Move datetime to next weekday (Monday)."""
        # Calculate days until Monday
        days_ahead = 0 - dt.weekday()  # Monday is 0
        if days_ahead <= 0:  # Already past Monday this week
            days_ahead += 7
        
        next_weekday = dt + timedelta(days=days_ahead)
        return next_weekday.replace(
            hour=self.posting_hour_start,
            minute=0,
            second=0,
            microsecond=0
        )
    
    def _move_to_next_day(self, dt: datetime) -> datetime:
        """Move datetime to next day's posting start."""
        next_day = dt + timedelta(days=1)
        return next_day.replace(
            hour=self.posting_hour_start,
            minute=0,
            second=0,
            microsecond=0
        )
    
    def _count_posts_on_day(self, scheduled_posts: List[ScheduledPost], target_date: date) -> int:
        """Count how many posts are scheduled for a specific day."""
        return sum(
            1 for post in scheduled_posts
            if post.scheduled_for.date() == target_date
        )
    
    def _get_last_scheduled_time_before(
        self,
        scheduled_posts: List[ScheduledPost],
        candidate_time: datetime
    ) -> Optional[datetime]:
        """Get the time of the last post scheduled before candidate_time."""
        posts_before = [
            post for post in scheduled_posts
            if post.scheduled_for < candidate_time
        ]
        
        if not posts_before:
            return None
        
        # Return the most recent one
        return max(post.scheduled_for for post in posts_before)
    
    def _calculate_priority(self, original_post: LinkedInPost) -> dict:
        """
        Calculate posting priority based on original post age (Golden Hour).
        
        Args:
            original_post: The original LinkedIn post
            
        Returns:
            dict with priority level, age, and emoji
        """
        if not original_post.original_post_date:
            # No date available - treat as normal priority
            return {
                'level': 'OK',
                'emoji': '⏰',
                'age_hours': None,
                'priority_score': 50  # Medium priority
            }
        
        # Calculate age in hours
        now = datetime.now()
        age = now - original_post.original_post_date
        age_hours = age.total_seconds() / 3600
        
        # Determine priority level
        if age_hours < self.golden_hour_urgent:
            # URGENT: Still in golden hour window - ride the engagement wave!
            level = 'URGENT'
            emoji = '🔥'
            priority_score = 100  # Highest priority
        elif age_hours < self.golden_hour_good:
            # GOOD: Still relevant, good engagement potential
            level = 'GOOD'
            emoji = '✅'
            priority_score = 75
        elif age_hours < self.golden_hour_ok:
            # OK: Acceptable, but engagement declining
            level = 'OK'
            emoji = '⏰'
            priority_score = 50
        else:
            # STALE: Old content, low engagement potential
            level = 'STALE'
            emoji = '⚠️ '
            priority_score = 25
        
        return {
            'level': level,
            'emoji': emoji,
            'age_hours': age_hours,
            'priority_score': priority_score
        }
    
    async def get_queue_summary(self, db: AsyncSession) -> dict:
        """
        Get summary of the current publish queue.
        
        Returns:
            dict with queue statistics and upcoming posts
        """
        log_operation_start(logger, "get_queue_summary")
        
        # Get all pending posts
        result = await db.execute(
            select(ScheduledPost)
            .where(ScheduledPost.status == ScheduledPostStatus.PENDING)
            .order_by(ScheduledPost.scheduled_for)
        )
        pending = list(result.scalars().all())
        
        now = datetime.now()
        today = now.date()
        week_from_now = now + timedelta(days=7)
        
        # Count posts today
        today_count = sum(1 for post in pending if post.scheduled_for.date() == today)
        
        # Count posts this week
        week_count = sum(
            1 for post in pending
            if post.scheduled_for <= week_from_now
        )
        
        # Get next scheduled time
        next_scheduled = pending[0].scheduled_for if pending else None
        
        log_operation_success(
            logger,
            "get_queue_summary",
            total=len(pending),
            today=today_count,
            week=week_count
        )
        
        return {
            "total_scheduled": len(pending),
            "pending_count": len(pending),
            "today_count": today_count,
            "this_week_count": week_count,
            "next_scheduled": next_scheduled,
            "queue": pending
        }
    
    async def reschedule_post(
        self,
        db: AsyncSession,
        scheduled_post_id: int,
        new_time: datetime
    ) -> ScheduledPost:
        """
        Reschedule a post to a different time.
        
        Args:
            db: Database session
            scheduled_post_id: ID of scheduled post
            new_time: New scheduled time
            
        Returns:
            Updated ScheduledPost
        """
        log_operation_start(logger, "reschedule_post", id=scheduled_post_id)
        
        result = await db.execute(
            select(ScheduledPost).where(ScheduledPost.id == scheduled_post_id)
        )
        scheduled_post = result.scalar_one_or_none()
        
        if not scheduled_post:
            raise ValueError(f"Scheduled post {scheduled_post_id} not found")
        
        if scheduled_post.status != ScheduledPostStatus.PENDING:
            raise ValueError(
                f"Cannot reschedule post in status {scheduled_post.status.value}"
            )
        
        old_time = scheduled_post.scheduled_for
        scheduled_post.scheduled_for = new_time
        
        await db.commit()
        await db.refresh(scheduled_post)
        
        logger.info(
            f"📅 Rescheduled post {scheduled_post_id}: "
            f"{old_time.strftime('%b %d %I:%M%p')} → "
            f"{new_time.strftime('%b %d %I:%M%p')}"
        )
        
        log_operation_success(logger, "reschedule_post", id=scheduled_post_id)
        
        return scheduled_post
    
    async def cancel_scheduled_post(
        self,
        db: AsyncSession,
        scheduled_post_id: int
    ) -> ScheduledPost:
        """
        Cancel a scheduled post.
        
        Args:
            db: Database session
            scheduled_post_id: ID of scheduled post
            
        Returns:
            Updated ScheduledPost
        """
        log_operation_start(logger, "cancel_scheduled_post", id=scheduled_post_id)
        
        result = await db.execute(
            select(ScheduledPost).where(ScheduledPost.id == scheduled_post_id)
        )
        scheduled_post = result.scalar_one_or_none()
        
        if not scheduled_post:
            raise ValueError(f"Scheduled post {scheduled_post_id} not found")
        
        if scheduled_post.status != ScheduledPostStatus.PENDING:
            raise ValueError(
                f"Cannot cancel post in status {scheduled_post.status.value}"
            )
        
        scheduled_post.status = ScheduledPostStatus.CANCELLED
        
        await db.commit()
        await db.refresh(scheduled_post)
        
        logger.info(f"❌ Cancelled scheduled post {scheduled_post_id}")
        
        log_operation_success(logger, "cancel_scheduled_post", id=scheduled_post_id)
        
        return scheduled_post


# Global scheduler instance
_scheduler: Optional[PostScheduler] = None


def get_scheduler() -> PostScheduler:
    """Get the global scheduler instance."""
    global _scheduler
    if _scheduler is None:
        _scheduler = PostScheduler()
    return _scheduler
