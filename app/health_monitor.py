"""System health monitoring and alerting."""
import logging
from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models import SystemHealth
from app.database import get_db

logger = logging.getLogger(__name__)


async def update_last_successful_post(db: Session) -> None:
    """Update the last successful post timestamp."""
    health = await get_or_create_health_record(db)
    health.last_successful_post_time = datetime.utcnow()
    health.total_posts_posted += 1
    health.updated_at = datetime.utcnow()
    
    # Clear alert if it was sent
    if health.health_alert_sent_at:
        health.health_alert_resolved_at = datetime.utcnow()
        logger.info("✅ System health restored - successful post completed")
    
    await db.commit()
    logger.debug(f"Updated last successful post time: {health.last_successful_post_time}")


async def update_last_successful_scrape(db: Session) -> None:
    """Update the last successful scrape timestamp."""
    health = await get_or_create_health_record(db)
    health.last_successful_scrape_time = datetime.utcnow()
    health.total_posts_scraped += 1
    health.updated_at = datetime.utcnow()
    await db.commit()
    logger.debug(f"Updated last successful scrape time: {health.last_successful_scrape_time}")


async def increment_failed_posts(db: Session) -> None:
    """Increment the failed posts counter."""
    health = await get_or_create_health_record(db)
    health.total_posts_failed += 1
    health.updated_at = datetime.utcnow()
    await db.commit()


async def get_or_create_health_record(db: Session) -> SystemHealth:
    """Get or create the system health record."""
    result = await db.execute(select(SystemHealth))
    health = result.scalars().first()
    
    if not health:
        health = SystemHealth()
        db.add(health)
        await db.commit()
        await db.refresh(health)
        logger.info("Created new system health record")
    
    return health


async def check_system_health(db: Session) -> dict:
    """
    Check system health and return status.
    
    Returns:
        dict with health status information
    """
    health = await get_or_create_health_record(db)
    
    now = datetime.utcnow()
    alert_threshold_hours = 48
    
    # Check if we haven't posted successfully in 48 hours
    needs_alert = False
    hours_since_post = None
    
    if health.last_successful_post_time:
        time_since_post = now - health.last_successful_post_time
        hours_since_post = time_since_post.total_seconds() / 3600
        
        if hours_since_post >= alert_threshold_hours:
            needs_alert = True
    else:
        # Never posted successfully
        needs_alert = True
    
    # Check if we've already sent an alert recently (don't spam)
    alert_already_sent = False
    if health.health_alert_sent_at:
        time_since_alert = now - health.health_alert_sent_at
        # Don't send another alert for 24 hours
        if time_since_alert.total_seconds() < 86400:  # 24 hours
            alert_already_sent = True
        # Reset if alert was resolved
        if health.health_alert_resolved_at and health.health_alert_resolved_at > health.health_alert_sent_at:
            alert_already_sent = False
    
    return {
        "healthy": not needs_alert,
        "needs_alert": needs_alert and not alert_already_sent,
        "last_successful_post": health.last_successful_post_time,
        "last_successful_scrape": health.last_successful_scrape_time,
        "hours_since_post": hours_since_post,
        "alert_threshold_hours": alert_threshold_hours,
        "total_posts_scraped": health.total_posts_scraped,
        "total_posts_posted": health.total_posts_posted,
        "total_posts_failed": health.total_posts_failed,
        "alert_sent_at": health.health_alert_sent_at,
        "alert_resolved_at": health.health_alert_resolved_at,
    }


async def send_health_alert(db: Session, admin_email: str) -> None:
    """
    Send a health alert email to admin.
    
    Args:
        db: Database session
        admin_email: Email address to send alert to
    """
    health = await get_or_create_health_record(db)
    health_status = await check_system_health(db)
    
    if not health_status["needs_alert"]:
        logger.debug("No health alert needed")
        return
    
    logger.warning("🚨 System health alert needed!")
    
    # TODO: Integrate with email service (Postal)
    # For now, just log the alert
    logger.error(
        f"⚠️  HEALTH ALERT: No successful posts in {health_status['hours_since_post']:.1f} hours "
        f"(threshold: {health_status['alert_threshold_hours']} hours)"
    )
    logger.error(f"   Last successful post: {health_status['last_successful_post']}")
    logger.error(f"   Total scraped: {health_status['total_posts_scraped']}")
    logger.error(f"   Total posted: {health_status['total_posts_posted']}")
    logger.error(f"   Total failed: {health_status['total_posts_failed']}")
    
    # Mark alert as sent
    health.health_alert_sent_at = datetime.utcnow()
    health.updated_at = datetime.utcnow()
    await db.commit()
    
    logger.info(f"Health alert logged (would send to: {admin_email})")
    
    # TODO: Actually send email when Postal integration is ready
    # await send_email(
    #     to=admin_email,
    #     subject="LinkedIn Reposter - System Health Alert",
    #     body=f"No successful posts in {health_status['hours_since_post']:.1f} hours"
    # )
