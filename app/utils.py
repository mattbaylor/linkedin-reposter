"""Utility functions for LinkedIn Reposter."""
import random
import time
from difflib import SequenceMatcher
from typing import Optional
import logging

logger = logging.getLogger(__name__)


# ============================================================================
# FUZZY MATCHING
# ============================================================================

def fuzzy_match(text1: str, text2: str, threshold: float = 0.80) -> bool:
    """
    Check if two texts are similar using fuzzy matching.
    
    Args:
        text1: First text to compare
        text2: Second text to compare
        threshold: Similarity threshold (0.0 to 1.0), default 0.80
        
    Returns:
        True if similarity >= threshold, False otherwise
    """
    # Normalize texts: lowercase, strip whitespace
    normalized1 = text1.lower().strip()
    normalized2 = text2.lower().strip()
    
    # Calculate similarity ratio
    similarity = SequenceMatcher(None, normalized1, normalized2).ratio()
    
    logger.debug(f"Fuzzy match similarity: {similarity:.2%} (threshold: {threshold:.2%})")
    
    return similarity >= threshold


def fuzzy_match_score(text1: str, text2: str) -> float:
    """
    Calculate similarity score between two texts.
    
    Args:
        text1: First text to compare
        text2: Second text to compare
        
    Returns:
        Similarity score between 0.0 and 1.0
    """
    normalized1 = text1.lower().strip()
    normalized2 = text2.lower().strip()
    
    return SequenceMatcher(None, normalized1, normalized2).ratio()


# ============================================================================
# HUMANIZATION - Random delays and timing
# ============================================================================

def random_delay(min_seconds: float = 1.0, max_seconds: float = 3.0) -> None:
    """
    Sleep for a random amount of time to simulate human behavior.
    
    Args:
        min_seconds: Minimum delay in seconds
        max_seconds: Maximum delay in seconds
    """
    delay = random.uniform(min_seconds, max_seconds)
    logger.debug(f"Random delay: {delay:.2f}s")
    time.sleep(delay)


def random_short_delay() -> None:
    """Quick random delay (0.5-1.5 seconds)."""
    random_delay(0.5, 1.5)


def random_medium_delay() -> None:
    """Medium random delay (2-4 seconds)."""
    random_delay(2.0, 4.0)


def random_long_delay() -> None:
    """Long random delay (5-8 seconds)."""
    random_delay(5.0, 8.0)


def random_profile_delay() -> None:
    """
    Very long random delay for between-profile scraping (1-3 minutes).
    Makes scraping behavior appear more human by adding realistic pauses.
    """
    delay_seconds = random.uniform(60.0, 180.0)  # 1-3 minutes
    delay_minutes = delay_seconds / 60
    logger.info(f"⏳ Human-like delay before next profile: {delay_minutes:.1f} minutes")
    random_delay(delay_seconds, delay_seconds)


def human_typing_delay() -> float:
    """
    Generate a realistic typing delay between characters.
    
    Returns:
        Delay in seconds (typically 0.05-0.15s)
    """
    # Average typing speed: ~60-80 WPM = ~5-7 chars/sec
    # Add some variation for realism
    base_delay = 0.08  # ~12.5 chars/sec
    variation = random.uniform(-0.03, 0.07)  # Add jitter
    
    return max(0.02, base_delay + variation)


# ============================================================================
# HUMANIZATION - Selenium typing simulation
# ============================================================================

def type_like_human(element, text: str, wpm: Optional[int] = None) -> None:
    """
    Type text into a Selenium element with human-like timing.
    
    Args:
        element: Selenium WebElement to type into
        text: Text to type
        wpm: Optional words per minute (default: random 40-70)
    """
    if wpm is None:
        wpm = random.randint(40, 70)  # Human typing speed variation
    
    # Calculate delay per character
    # WPM = words/minute, avg 5 chars/word
    chars_per_second = (wpm * 5) / 60
    base_delay = 1.0 / chars_per_second
    
    logger.debug(f"Typing {len(text)} chars at ~{wpm} WPM")
    
    for char in text:
        element.send_keys(char)
        
        # Add variation to delay
        variation = random.uniform(-0.02, 0.03)
        delay = max(0.01, base_delay + variation)
        
        # Occasional longer pauses (thinking/hesitation)
        if random.random() < 0.05:  # 5% chance
            delay += random.uniform(0.3, 0.8)
        
        time.sleep(delay)


def random_scroll_amount() -> int:
    """
    Generate a random scroll amount in pixels.
    
    Returns:
        Random scroll distance (300-800 pixels)
    """
    return random.randint(300, 800)


def human_scroll_delay() -> None:
    """Delay between scroll actions (0.8-2.0 seconds)."""
    random_delay(0.8, 2.0)


# ============================================================================
# CONTENT VALIDATION
# ============================================================================

def is_repost_content(text: str) -> bool:
    """
    Check if content appears to be a repost/reshare based on common indicators.
    
    Args:
        text: Post content to check
        
    Returns:
        True if content looks like a repost, False otherwise
    """
    repost_indicators = [
        "reposted this",
        "shared this",
        "reshared",
        "re-shared",
        "repost from",
        "originally posted by",
    ]
    
    text_lower = text.lower()
    
    for indicator in repost_indicators:
        if indicator in text_lower:
            logger.debug(f"Detected repost indicator: '{indicator}'")
            return True
    
    return False


def truncate_text(text: str, max_length: int = 100, suffix: str = "...") -> str:
    """
    Truncate text to a maximum length.
    
    Args:
        text: Text to truncate
        max_length: Maximum length (including suffix)
        suffix: Suffix to add if truncated
        
    Returns:
        Truncated text
    """
    if len(text) <= max_length:
        return text
    
    return text[:max_length - len(suffix)] + suffix
