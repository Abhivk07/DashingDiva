"""
Base scraper class and common functionality for all retailer scrapers.
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import List, Optional
from urllib.parse import urlparse

import aiohttp

from ..models.review import ReviewData
from ..utils.helpers import RateLimiter, UserAgentRotator

logger = logging.getLogger(__name__)


class BaseRetailerScraper(ABC):
    """
    Abstract base class for retailer-specific scrapers.

    This class provides common functionality and enforces a consistent
    interface for all retailer scrapers.
    """

    def __init__(self, rate_limiter: RateLimiter):
        """
        Initialize base scraper.

        Args:
            rate_limiter: Rate limiter instance for controlling request frequency
        """
        self.rate_limiter = rate_limiter
        self.user_agent_rotator = UserAgentRotator()
        self.session: Optional[aiohttp.ClientSession] = None
        self.retailer_name = "Unknown"

    async def __aenter__(self):
        """Async context manager entry."""
        connector = aiohttp.TCPConnector(
            limit=10, limit_per_host=5, ttl_dns_cache=300, use_dns_cache=True
        )

        timeout = aiohttp.ClientTimeout(total=30, connect=10)

        headers = {
            "User-Agent": self.user_agent_rotator.get_random_agent(),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }

        self.session = aiohttp.ClientSession(connector=connector, timeout=timeout, headers=headers)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.session:
            await self.session.close()

    @abstractmethod
    async def scrape_product_reviews(self, product_url: str) -> List[ReviewData]:
        """
        Scrape reviews for a specific product.

        Args:
            product_url: URL of the product page

        Returns:
            List of ReviewData objects
        """
        pass

    @abstractmethod
    def extract_product_id(self, url: str) -> str:
        """
        Extract product ID from product URL.

        Args:
            url: Product URL

        Returns:
            Product ID string
        """
        pass

    async def fetch_page(self, url: str) -> Optional[str]:
        """
        Fetch webpage content with rate limiting and error handling.

        Args:
            url: URL to fetch

        Returns:
            HTML content or None if failed
        """
        await self.rate_limiter.wait_if_needed()

        try:
            # Rotate user agent for each request
            headers = {"User-Agent": self.user_agent_rotator.get_rotating_agent()}

            async with self.session.get(url, headers=headers) as response:
                if response.status == 200:
                    return await response.text()
                elif response.status == 429:  # Too Many Requests
                    logger.warning(f"Rate limited by {url}. Status: {response.status}")
                    await asyncio.sleep(60)  # Wait longer before retrying
                    return None
                else:
                    logger.error(f"Failed to fetch {url}: HTTP {response.status}")
                    return None

        except asyncio.TimeoutError:
            logger.error(f"Timeout fetching {url}")
            return None
        except Exception as e:
            logger.error(f"Error fetching {url}: {e}")
            return None

    def validate_url(self, url: str) -> bool:
        """
        Validate if URL belongs to this retailer.

        Args:
            url: URL to validate

        Returns:
            True if URL is valid for this retailer
        """
        try:
            parsed = urlparse(url)
            return parsed.netloc.lower().endswith(self.get_domain())
        except Exception:
            return False

    @abstractmethod
    def get_domain(self) -> str:
        """
        Get the domain name for this retailer.

        Returns:
            Domain name (e.g., 'walmart.com')
        """
        pass

    def get_retailer_name(self) -> str:
        """Get the retailer name."""
        return self.retailer_name
