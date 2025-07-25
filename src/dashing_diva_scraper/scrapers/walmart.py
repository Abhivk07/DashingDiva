"""
Walmart-specific scraper implementation.
"""

import json
import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from bs4 import BeautifulSoup

from ..models.review import ReviewData
from ..utils.helpers import generate_review_id, sanitize_text
from .base import BaseRetailerScraper

logger = logging.getLogger(__name__)


class WalmartScraper(BaseRetailerScraper):
    """
    Walmart-specific implementation of the review scraper.

    Handles Walmart's specific page structure, API endpoints,
    and data formats for extracting customer reviews.
    """

    def __init__(self, rate_limiter):
        super().__init__(rate_limiter)
        self.retailer_name = "Walmart"

    def get_domain(self) -> str:
        """Get Walmart domain."""
        return "walmart.com"

    def extract_product_id(self, url: str) -> str:
        """
        Extract product ID from Walmart URL.

        Walmart URLs typically follow patterns like:
        - /ip/product-name/12345
        - /ip/product-name/12345?param=value
        """
        # Match pattern: /ip/anything/numbers
        match = re.search(r"/ip/[^/]+/(\d+)", url)
        if match:
            return match.group(1)

        # Fallback: try to extract from query parameters
        match = re.search(r"[?&]id=(\d+)", url)
        if match:
            return match.group(1)

        # Last resort: use URL path
        return url.split("/")[-1].split("?")[0]

    async def scrape_product_reviews(self, product_url: str) -> List[ReviewData]:
        """
        Scrape reviews from Walmart product page.

        Args:
            product_url: Walmart product page URL

        Returns:
            List of ReviewData objects
        """
        if not self.validate_url(product_url):
            logger.error(f"Invalid Walmart URL: {product_url}")
            return []

        html_content = await self.fetch_page(product_url)
        if not html_content:
            logger.error(f"Failed to fetch content from {product_url}")
            return []

        try:
            soup = BeautifulSoup(html_content, "html.parser")

            # Extract product information
            product_id = self.extract_product_id(product_url)
            product_name = self._extract_product_name(soup)

            # Try multiple methods to find reviews
            reviews = []

            # Method 1: Parse JSON-LD structured data
            json_reviews = self._extract_reviews_from_json_ld(
                soup, product_id, product_name, product_url
            )
            reviews.extend(json_reviews)

            # Method 2: Parse HTML review containers
            html_reviews = self._extract_reviews_from_html(
                soup, product_id, product_name, product_url
            )
            reviews.extend(html_reviews)

            # Method 3: Look for AJAX/API data in script tags
            script_reviews = self._extract_reviews_from_scripts(
                soup, product_id, product_name, product_url
            )
            reviews.extend(script_reviews)

            # Remove duplicates based on review_id
            unique_reviews = self._deduplicate_reviews(reviews)

            logger.info(f"Scraped {len(unique_reviews)} reviews from {product_url}")
            return unique_reviews

        except Exception as e:
            logger.error(f"Error scraping reviews from {product_url}: {e}")
            return []

    def _extract_product_name(self, soup: BeautifulSoup) -> str:
        """Extract product name from Walmart page."""
        # Try multiple selectors in order of preference
        selectors = [
            'h1[data-automation-id="product-title"]',
            "h1.f1",
            ".product-title h1",
            "h1",
            '[data-testid="product-title"]',
        ]

        for selector in selectors:
            element = soup.select_one(selector)
            if element:
                name = sanitize_text(element.get_text())
                if name:
                    return name

        return "Unknown Product"

    def _extract_reviews_from_json_ld(
        self, soup: BeautifulSoup, product_id: str, product_name: str, product_url: str
    ) -> List[ReviewData]:
        """Extract reviews from JSON-LD structured data."""
        reviews = []

        # Look for JSON-LD script tags
        json_ld_scripts = soup.find_all("script", type="application/ld+json")

        for script in json_ld_scripts:
            try:
                data = json.loads(script.string)

                # Handle both single objects and arrays
                if isinstance(data, list):
                    for item in data:
                        reviews.extend(
                            self._parse_json_ld_item(item, product_id, product_name, product_url)
                        )
                else:
                    reviews.extend(
                        self._parse_json_ld_item(data, product_id, product_name, product_url)
                    )

            except (json.JSONDecodeError, AttributeError) as e:
                logger.debug(f"Failed to parse JSON-LD: {e}")
                continue

        return reviews

    def _parse_json_ld_item(
        self, data: Dict[Any, Any], product_id: str, product_name: str, product_url: str
    ) -> List[ReviewData]:
        """Parse a single JSON-LD item for review data."""
        reviews = []

        # Look for review data in various locations
        if isinstance(data, dict):
            # Direct review object
            if data.get("@type") == "Review":
                review = self._create_review_from_json(data, product_id, product_name, product_url)
                if review:
                    reviews.append(review)

            # Product with aggregated reviews
            elif "review" in data:
                review_data = data["review"]
                if isinstance(review_data, list):
                    for review_item in review_data:
                        review = self._create_review_from_json(
                            review_item, product_id, product_name, product_url
                        )
                        if review:
                            reviews.append(review)
                else:
                    review = self._create_review_from_json(
                        review_data, product_id, product_name, product_url
                    )
                    if review:
                        reviews.append(review)

        return reviews

    def _extract_reviews_from_html(
        self, soup: BeautifulSoup, product_id: str, product_name: str, product_url: str
    ) -> List[ReviewData]:
        """Extract reviews from HTML elements."""
        reviews = []

        # Common review container selectors for Walmart
        review_selectors = [
            '[data-testid*="review"]',
            ".review-item",
            ".customer-review",
            '[class*="review"]',
        ]

        for selector in review_selectors:
            containers = soup.select(selector)
            for container in containers:
                try:
                    review = self._parse_html_review_container(
                        container, product_id, product_name, product_url
                    )
                    if review:
                        reviews.append(review)
                except Exception as e:
                    logger.debug(f"Error parsing HTML review container: {e}")
                    continue

        return reviews

    def _parse_html_review_container(
        self, container, product_id: str, product_name: str, product_url: str
    ) -> Optional[ReviewData]:
        """Parse a single HTML review container."""
        try:
            # Extract rating
            rating = self._extract_rating_from_html(container)

            # Extract reviewer name
            reviewer_name = self._extract_reviewer_name(container)

            # Extract review text
            review_text = self._extract_review_text(container)

            # Extract review title
            review_title = self._extract_review_title(container)

            # Skip if no meaningful content
            if not review_text and not review_title:
                return None

            # Extract additional metadata
            review_date = self._extract_review_date(container)
            verified_purchase = self._extract_verified_status(container)
            helpful_votes = self._extract_helpful_votes(container)

            # Generate unique review ID
            review_id = generate_review_id(product_id, reviewer_name, review_text)

            return ReviewData(
                product_id=product_id,
                product_name=product_name,
                product_url=product_url,
                reviewer_name=reviewer_name,
                rating=rating,
                review_title=review_title,
                review_text=review_text,
                review_date=review_date,
                verified_purchase=verified_purchase,
                helpful_votes=helpful_votes,
                retailer=self.retailer_name,
                scraped_at=datetime.now().isoformat(),
                review_id=review_id,
            )

        except Exception as e:
            logger.debug(f"Error parsing HTML review: {e}")
            return None

    def _extract_rating_from_html(self, container) -> float:
        """Extract numerical rating from HTML container."""
        # Try various methods to find rating

        # Method 1: Look for aria-label with rating
        rating_elements = container.find_all(attrs={"aria-label": re.compile(r"star|rating", re.I)})
        for element in rating_elements:
            aria_label = element.get("aria-label", "")
            match = re.search(r"(\d+(?:\.\d+)?)", aria_label)
            if match:
                return float(match.group(1))

        # Method 2: Look for data attributes
        for attr in ["data-rating", "data-value", "data-score"]:
            element = container.find(attrs={attr: True})
            if element:
                try:
                    return float(element[attr])
                except (ValueError, TypeError):
                    continue

        # Method 3: Count filled stars
        star_elements = container.find_all(class_=re.compile(r"star.*filled|filled.*star", re.I))
        if star_elements:
            return float(len(star_elements))

        return 0.0

    def _extract_reviewer_name(self, container) -> str:
        """Extract reviewer name from container."""
        selectors = [
            '[data-testid*="reviewer"]',
            ".reviewer-name",
            ".customer-name",
            '[class*="reviewer"]',
            '[class*="author"]',
        ]

        for selector in selectors:
            element = container.select_one(selector)
            if element:
                name = sanitize_text(element.get_text())
                if name:
                    return name

        return "Anonymous"

    def _extract_review_text(self, container) -> str:
        """Extract review text content."""
        selectors = [
            '[data-testid*="review-text"]',
            ".review-text",
            ".review-content",
            ".customer-review-text",
            '[class*="review-body"]',
        ]

        for selector in selectors:
            element = container.select_one(selector)
            if element:
                text = sanitize_text(element.get_text())
                if text:
                    return text

        return ""

    def _extract_review_title(self, container) -> str:
        """Extract review title."""
        selectors = [
            '[data-testid*="review-title"]',
            ".review-title",
            ".review-headline",
            "h3",
            "h4",
            "h5",
        ]

        for selector in selectors:
            element = container.select_one(selector)
            if element:
                title = sanitize_text(element.get_text())
                if title and len(title) < 200:  # Reasonable title length
                    return title

        return ""

    def _extract_review_date(self, container) -> str:
        """Extract review date."""
        selectors = ['[data-testid*="date"]', ".review-date", ".date-posted", "time"]

        for selector in selectors:
            element = container.select_one(selector)
            if element:
                date_text = sanitize_text(element.get_text())
                if date_text:
                    return date_text

                # Check for datetime attribute
                datetime_attr = element.get("datetime")
                if datetime_attr:
                    return datetime_attr

        return datetime.now().isoformat()

    def _extract_verified_status(self, container) -> bool:
        """Check if purchase is verified."""
        verified_indicators = ["verified purchase", "verified buyer", "confirmed purchase"]

        text_content = container.get_text().lower()
        return any(indicator in text_content for indicator in verified_indicators)

    def _extract_helpful_votes(self, container) -> int:
        """Extract helpful votes count."""
        selectors = ['[data-testid*="helpful"]', ".helpful-count", ".votes-helpful"]

        for selector in selectors:
            element = container.select_one(selector)
            if element:
                text = element.get_text()
                match = re.search(r"(\d+)", text)
                if match:
                    return int(match.group(1))

        return 0

    def _extract_reviews_from_scripts(
        self, soup: BeautifulSoup, product_id: str, product_name: str, product_url: str
    ) -> List[ReviewData]:
        """Extract reviews from JavaScript/AJAX data in script tags."""
        reviews = []

        # Look for script tags with JSON data
        script_tags = soup.find_all("script")

        for script in script_tags:
            if not script.string:
                continue

            try:
                # Look for patterns that might contain review data
                if "review" in script.string.lower():
                    # Try to extract JSON objects
                    json_matches = re.findall(
                        r'\{[^}]*"review"[^}]*\}', script.string, re.IGNORECASE
                    )

                    for json_str in json_matches:
                        try:
                            data = json.loads(json_str)
                            review = self._create_review_from_json(
                                data, product_id, product_name, product_url
                            )
                            if review:
                                reviews.append(review)
                        except json.JSONDecodeError:
                            continue

            except Exception as e:
                logger.debug(f"Error parsing script tag: {e}")
                continue

        return reviews

    def _create_review_from_json(
        self, review_data: Dict, product_id: str, product_name: str, product_url: str
    ) -> Optional[ReviewData]:
        """Create ReviewData from JSON review object."""
        try:
            # Extract data with various possible key names
            author_data = review_data.get("author", {})
            if isinstance(author_data, str):
                reviewer_name = author_data
            else:
                reviewer_name = author_data.get("name", "Anonymous")

            # Rating can be in different formats
            rating_data = review_data.get("reviewRating", review_data.get("rating", {}))
            if isinstance(rating_data, (int, float)):
                rating = float(rating_data)
            else:
                rating = float(rating_data.get("ratingValue", 0))

            review_text = sanitize_text(
                review_data.get("reviewBody", review_data.get("description", ""))
            )
            review_title = sanitize_text(review_data.get("name", review_data.get("headline", "")))

            # Skip if no meaningful content
            if not review_text and not review_title:
                return None

            # Date handling
            review_date = review_data.get("datePublished", review_data.get("dateCreated", ""))
            if not review_date:
                review_date = datetime.now().isoformat()

            review_id = generate_review_id(product_id, reviewer_name, review_text)

            return ReviewData(
                product_id=product_id,
                product_name=product_name,
                product_url=product_url,
                reviewer_name=reviewer_name,
                rating=rating,
                review_title=review_title,
                review_text=review_text,
                review_date=review_date,
                verified_purchase=review_data.get("verifiedPurchase", False),
                helpful_votes=0,  # Not usually available in JSON-LD
                retailer=self.retailer_name,
                scraped_at=datetime.now().isoformat(),
                review_id=review_id,
            )

        except (KeyError, ValueError, TypeError) as e:
            logger.debug(f"Error creating review from JSON: {e}")
            return None

    def _deduplicate_reviews(self, reviews: List[ReviewData]) -> List[ReviewData]:
        """Remove duplicate reviews based on review_id."""
        seen_ids = set()
        unique_reviews = []

        for review in reviews:
            if review.review_id not in seen_ids:
                seen_ids.add(review.review_id)
                unique_reviews.append(review)

        return unique_reviews
