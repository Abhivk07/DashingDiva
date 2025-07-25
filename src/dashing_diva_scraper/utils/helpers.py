"""
Utility functions and classes for the Dashing Diva review scraper.
"""

import asyncio
import hashlib
import logging
import time
from typing import List

from fake_useragent import UserAgent

logger = logging.getLogger(__name__)


class RateLimiter:
    """
    Rate limiter to avoid overwhelming target servers and respect robots.txt.

    Implements a sliding window rate limiting algorithm to ensure
    we don't exceed the specified request rate.
    """

    def __init__(self, max_requests: int = 10, time_window: int = 60):
        """
        Initialize rate limiter.

        Args:
            max_requests: Maximum requests allowed in time window
            time_window: Time window in seconds
        """
        self.max_requests = max_requests
        self.time_window = time_window
        self.requests = []
        self._lock = asyncio.Lock()

    async def wait_if_needed(self):
        """Wait if rate limit would be exceeded."""
        async with self._lock:
            now = time.time()

            # Remove old requests outside time window
            self.requests = [
                req_time for req_time in self.requests if now - req_time < self.time_window
            ]

            if len(self.requests) >= self.max_requests:
                sleep_time = self.time_window - (now - self.requests[0])
                if sleep_time > 0:
                    logger.info(f"Rate limit reached. Sleeping for {sleep_time:.2f} seconds")
                    await asyncio.sleep(sleep_time)

            self.requests.append(now)


class UserAgentRotator:
    """
    Rotates user agents to avoid detection and blocking.
    """

    def __init__(self):
        self.ua = UserAgent()
        self._current_agents = []
        self._index = 0

    def get_random_agent(self) -> str:
        """Get a random user agent string."""
        return self.ua.random

    def get_rotating_agent(self) -> str:
        """Get user agent using rotation strategy."""
        if not self._current_agents:
            # Initialize with a set of common user agents
            self._current_agents = [self.ua.chrome, self.ua.firefox, self.ua.safari, self.ua.edge]

        agent = self._current_agents[self._index]
        self._index = (self._index + 1) % len(self._current_agents)
        return agent


def generate_review_id(product_id: str, reviewer_name: str, review_text: str) -> str:
    """
    Generate a unique review ID based on review content.

    This helps prevent duplicate reviews from being stored.

    Args:
        product_id: Product identifier
        reviewer_name: Name of the reviewer
        review_text: Review content

    Returns:
        Unique review ID (MD5 hash)
    """
    content = f"{product_id}_{reviewer_name}_{review_text}"
    return hashlib.md5(content.encode("utf-8")).hexdigest()


def validate_url(url: str) -> bool:
    """
    Validate if URL is from a supported retailer.

    Args:
        url: URL to validate

    Returns:
        True if URL is valid and supported
    """
    supported_domains = ["walmart.com", "target.com", "ulta.com"]

    url_lower = url.lower()
    return any(domain in url_lower for domain in supported_domains)


def sanitize_text(text: str) -> str:
    """
    Clean and sanitize text content.

    Args:
        text: Raw text to clean

    Returns:
        Cleaned text
    """
    if not text:
        return ""

    # Remove extra whitespace and normalize
    text = " ".join(text.split())

    # Remove or replace problematic characters
    text = text.replace("\x00", "")  # Remove null bytes
    text = text.replace("\r\n", "\n")  # Normalize line endings

    return text.strip()


async def retry_async(func, max_retries: int = 3, delay: float = 1.0, backoff: float = 2.0):
    """
    Retry an async function with exponential backoff.

    Args:
        func: Async function to retry
        max_retries: Maximum number of retry attempts
        delay: Initial delay between retries
        backoff: Backoff multiplier

    Returns:
        Function result or raises last exception
    """
    last_exception = None

    for attempt in range(max_retries + 1):
        try:
            return await func()
        except Exception as e:
            last_exception = e

            if attempt < max_retries:
                wait_time = delay * (backoff**attempt)
                logger.warning(f"Attempt {attempt + 1} failed: {e}. Retrying in {wait_time:.2f}s")
                await asyncio.sleep(wait_time)
            else:
                logger.error(f"All {max_retries + 1} attempts failed")

    raise last_exception


def batch_list(items: List, batch_size: int = 10):
    """
    Split a list into batches of specified size.

    Args:
        items: List to split
        batch_size: Size of each batch

    Yields:
        Batches of items
    """
    for i in range(0, len(items), batch_size):
        yield items[i : i + batch_size]
