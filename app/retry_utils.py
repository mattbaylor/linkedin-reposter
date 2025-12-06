"""Retry utilities with exponential backoff for external API calls."""
import asyncio
import logging
import random
from typing import TypeVar, Callable, Any, Optional
from functools import wraps

logger = logging.getLogger(__name__)

T = TypeVar('T')


async def retry_with_backoff(
    func: Callable[..., T],
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    jitter: bool = True,
    exceptions: tuple = (Exception,),
    operation_name: Optional[str] = None
) -> T:
    """
    Retry an async function with exponential backoff.
    
    Args:
        func: Async function to retry
        max_retries: Maximum number of retry attempts
        base_delay: Initial delay in seconds
        max_delay: Maximum delay in seconds
        exponential_base: Base for exponential backoff
        jitter: Whether to add random jitter to delays
        exceptions: Tuple of exceptions to catch and retry
        operation_name: Optional name for logging
        
    Returns:
        Result of the function call
        
    Raises:
        The last exception if all retries fail
    """
    name = operation_name or func.__name__
    last_exception = None
    
    for attempt in range(max_retries + 1):
        try:
            result = await func()
            if attempt > 0:
                logger.info(f"✅ {name} succeeded on attempt {attempt + 1}")
            return result
        except exceptions as e:
            last_exception = e
            
            if attempt >= max_retries:
                logger.error(f"❌ {name} failed after {max_retries + 1} attempts: {e}")
                raise
            
            # Calculate delay with exponential backoff
            delay = min(base_delay * (exponential_base ** attempt), max_delay)
            
            # Add jitter to prevent thundering herd
            if jitter:
                delay = delay * (0.5 + random.random())
            
            logger.warning(
                f"⚠️  {name} failed (attempt {attempt + 1}/{max_retries + 1}): {e}. "
                f"Retrying in {delay:.2f}s..."
            )
            
            await asyncio.sleep(delay)
    
    # This shouldn't be reached, but for type safety
    raise last_exception


def async_retry(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    jitter: bool = True,
    exceptions: tuple = (Exception,)
):
    """
    Decorator for async functions to add retry with exponential backoff.
    
    Usage:
        @async_retry(max_retries=3, base_delay=1.0)
        async def my_api_call():
            # Your code here
            pass
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            async def attempt():
                return await func(*args, **kwargs)
            
            return await retry_with_backoff(
                attempt,
                max_retries=max_retries,
                base_delay=base_delay,
                max_delay=max_delay,
                exponential_base=exponential_base,
                jitter=jitter,
                exceptions=exceptions,
                operation_name=func.__name__
            )
        
        return wrapper
    return decorator


# Sync version for Selenium/threadpool contexts
def retry_with_backoff_sync(
    func: Callable[..., T],
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    jitter: bool = True,
    exceptions: tuple = (Exception,),
    operation_name: Optional[str] = None
) -> T:
    """
    Retry a synchronous function with exponential backoff.
    
    Args:
        func: Synchronous function to retry
        max_retries: Maximum number of retry attempts
        base_delay: Initial delay in seconds
        max_delay: Maximum delay in seconds
        exponential_base: Base for exponential backoff
        jitter: Whether to add random jitter to delays
        exceptions: Tuple of exceptions to catch and retry
        operation_name: Optional name for logging
        
    Returns:
        Result of the function call
        
    Raises:
        The last exception if all retries fail
    """
    import time
    
    name = operation_name or func.__name__
    last_exception = None
    
    for attempt in range(max_retries + 1):
        try:
            result = func()
            if attempt > 0:
                logger.info(f"✅ {name} succeeded on attempt {attempt + 1}")
            return result
        except exceptions as e:
            last_exception = e
            
            if attempt >= max_retries:
                logger.error(f"❌ {name} failed after {max_retries + 1} attempts: {e}")
                raise
            
            # Calculate delay with exponential backoff
            delay = min(base_delay * (exponential_base ** attempt), max_delay)
            
            # Add jitter to prevent thundering herd
            if jitter:
                delay = delay * (0.5 + random.random())
            
            logger.warning(
                f"⚠️  {name} failed (attempt {attempt + 1}/{max_retries + 1}): {e}. "
                f"Retrying in {delay:.2f}s..."
            )
            
            time.sleep(delay)
    
    # This shouldn't be reached, but for type safety
    raise last_exception


def sync_retry(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    jitter: bool = True,
    exceptions: tuple = (Exception,)
):
    """
    Decorator for sync functions to add retry with exponential backoff.
    
    Usage:
        @sync_retry(max_retries=3, base_delay=1.0)
        def my_api_call():
            # Your code here
            pass
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            def attempt():
                return func(*args, **kwargs)
            
            return retry_with_backoff_sync(
                attempt,
                max_retries=max_retries,
                base_delay=base_delay,
                max_delay=max_delay,
                exponential_base=exponential_base,
                jitter=jitter,
                exceptions=exceptions,
                operation_name=func.__name__
            )
        
        return wrapper
    return decorator
