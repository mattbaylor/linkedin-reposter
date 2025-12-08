"""Chrome operation lock manager for preventing concurrent browser access."""
import asyncio
import logging
from datetime import datetime
from typing import Optional, Dict, Any
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ChromeLockStatus:
    """Status information about Chrome lock."""
    is_locked: bool = False
    operation: Optional[str] = None  # e.g., "scraping", "posting", "manual_login"
    started_at: Optional[datetime] = None
    current_progress: Optional[str] = None  # e.g., "Processing @handle 3/10"
    locked_by: Optional[str] = None  # Task/request ID for debugging
    

class ChromeLockManager:
    """
    Global lock manager for Chrome/Selenium operations.
    
    Ensures only one Chrome operation happens at a time:
    - Scraping posts from profiles
    - Posting to LinkedIn
    - Manual login attempts
    - Email approval actions
    
    Uses asyncio.Lock for thread-safe operation coordination.
    Provides status tracking for admin dashboard visibility.
    """
    
    def __init__(self):
        self._lock = asyncio.Lock()
        self._status = ChromeLockStatus()
        self._waiters = 0  # Number of tasks waiting for lock
        
    @property
    def status(self) -> ChromeLockStatus:
        """Get current lock status (read-only)."""
        return ChromeLockStatus(
            is_locked=self._status.is_locked,
            operation=self._status.operation,
            started_at=self._status.started_at,
            current_progress=self._status.current_progress,
            locked_by=self._status.locked_by
        )
    
    @property
    def waiters_count(self) -> int:
        """Get number of tasks waiting for the lock."""
        return self._waiters
    
    async def acquire(self, operation: str, locked_by: str = "unknown") -> None:
        """
        Acquire the Chrome lock for an operation.
        
        Args:
            operation: Description of operation (e.g., "scraping", "posting")
            locked_by: Identifier for debugging (task ID, endpoint name, etc.)
        """
        self._waiters += 1
        try:
            logger.info(f"🔒 [{locked_by}] Waiting for Chrome lock... ({self._waiters} waiting)")
            await self._lock.acquire()
            
            self._status.is_locked = True
            self._status.operation = operation
            self._status.started_at = datetime.now()
            self._status.current_progress = None
            self._status.locked_by = locked_by
            
            logger.info(f"✅ [{locked_by}] Chrome lock acquired for: {operation}")
        finally:
            self._waiters -= 1
    
    def release(self) -> None:
        """Release the Chrome lock."""
        if self._lock.locked():
            locked_by = self._status.locked_by
            operation = self._status.operation
            
            self._status.is_locked = False
            self._status.operation = None
            self._status.started_at = None
            self._status.current_progress = None
            self._status.locked_by = None
            
            self._lock.release()
            logger.info(f"🔓 [{locked_by}] Chrome lock released for: {operation}")
    
    def update_progress(self, progress: str) -> None:
        """
        Update current operation progress (e.g., "Processing @handle 3/10").
        
        Args:
            progress: Human-readable progress string
        """
        if self._status.is_locked:
            self._status.current_progress = progress
            logger.debug(f"📊 Progress update: {progress}")
    
    def get_status_dict(self) -> Dict[str, Any]:
        """
        Get lock status as dictionary for API responses.
        
        Returns:
            dict: Status information including lock state, operation, progress, etc.
        """
        status = self.status
        elapsed_seconds = None
        
        if status.started_at:
            elapsed_seconds = int((datetime.now() - status.started_at).total_seconds())
        
        return {
            "is_locked": status.is_locked,
            "operation": status.operation,
            "started_at": status.started_at.isoformat() if status.started_at else None,
            "elapsed_seconds": elapsed_seconds,
            "current_progress": status.current_progress,
            "locked_by": status.locked_by,
            "waiters": self._waiters
        }


# Global singleton instance
_chrome_lock_manager: Optional[ChromeLockManager] = None


def get_chrome_lock() -> ChromeLockManager:
    """Get the global Chrome lock manager singleton."""
    global _chrome_lock_manager
    if _chrome_lock_manager is None:
        _chrome_lock_manager = ChromeLockManager()
    return _chrome_lock_manager
