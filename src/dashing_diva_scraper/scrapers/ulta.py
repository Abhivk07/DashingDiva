"""
ULTA-specific scraper implementation.
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


class UltaScraper(BaseRetailerScraper):
    """
    ULTA-specific implementation of the review scraper.

    Handles ULTA's specific page structure, API endpoints,
    and data formats for extracting customer reviews.
    """

    def __init__(self, rate_limiter):
        super().__init__(rate_limiter)
        self.retailer_name = "ULTA"

    def get_domain(self) -> str:
        """Get ULTA domain."""
        return "ulta.com"

    def extract_product_id(self, url: str) -> str:
        """
        Extract product ID from ULTA URL.

        ULTA URLs typically follow patterns like:
        - /p/product-name-pimprod123456?sku=123456
        """
        # Match pattern: pimprod followed by numbers
        match = re.search(r"pimprod(\d+)", url)
        if match:
            return match.group(1)

        # Fallback: try to extract from sku parameter
        match = re.search(r"[?&]sku=(\d+)", url)
        if match:
            return match.group(1)

        logger.warning(f"Could not extract product ID from ULTA URL: {url}")
        return ""

    async def scrape_product_reviews(self, product_url: str) -> List[ReviewData]:
        """
        Scrape reviews from ULTA product page.

        Args:
            product_url: ULTA product page URL

        Returns:
            List of ReviewData objects
        """
        if not self.validate_url(product_url):
            logger.error(f"Invalid ULTA URL: {product_url}")
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

            # Method 3: Look for ULTA-specific review sections
            ulta_reviews = self._extract_ulta_reviews(
                soup, product_id, product_name, product_url
            )
            reviews.extend(ulta_reviews)

            # Method 4: Look for PowerReviews (commonly used by ULTA)
            powerreviews = self._extract_powerreviews(
                soup, product_id, product_name, product_url
            )
            reviews.extend(powerreviews)

            # Remove duplicates based on review_id
            unique_reviews = self._deduplicate_reviews(reviews)

            logger.info(f"Scraped {len(unique_reviews)} reviews from {product_url}")
            return unique_reviews

        except Exception as e:
            logger.error(f"Error scraping reviews from {product_url}: {e}")
            return []

    def _extract_product_name(self, soup: BeautifulSoup) -> str:
        """Extract product name from ULTA page."""
        # Try multiple selectors in order of preference
        selectors = [
            'h1[data-comp="DisplayName "]',
            "h1.prod-title",
            ".product-title h1",
            "h1.h1",
            "h1",
        ]

        for selector in selectors:
            element = soup.select_one(selector)
            if element:
                return sanitize_text(element.get_text())

        logger.warning("Could not extract product name from ULTA page")
        return "Unknown Product"

    def _extract_ulta_reviews(
        self, soup: BeautifulSoup, product_id: str, product_name: str, product_url: str
    ) -> List[ReviewData]:
        """Extract reviews from ULTA-specific HTML structure."""
        reviews = []

        # ULTA uses various selectors for reviews
        review_selectors = [
            ".review-item",
            ".pr-review",
            "[data-testid^='review']",
            ".review-content",
        ]

        for selector in review_selectors:
            review_elements = soup.select(selector)
            for element in review_elements:
                try:
                    review = self._parse_ulta_review_element(
                        element, product_id, product_name, product_url
                    )
                    if review:
                        reviews.append(review)
                except Exception as e:
                    logger.debug(f"Error parsing ULTA review element: {e}")
                    continue

        return reviews

    def _extract_powerreviews(
        self, soup: BeautifulSoup, product_id: str, product_name: str, product_url: str
    ) -> List[ReviewData]:
        """Extract PowerReviews data commonly used by ULTA."""
        reviews = []

        # Look for PowerReviews containers
        powerreview_selectors = [
            ".pr-review-wrap",
            ".pr-review-author-date",
            "[data-pr-review-id]",
        ]

        for selector in powerreview_selectors:
            review_elements = soup.select(selector)
            for element in review_elements:
                try:
                    review = self._parse_powerreview_element(
                        element, product_id, product_name, product_url
                    )
                    if review:
                        reviews.append(review)
                except Exception as e:
                    logger.debug(f"Error parsing PowerReview element: {e}")
                    continue

        return reviews

    def _parse_ulta_review_element(
        self, element, product_id: str, product_name: str, product_url: str
    ) -> Optional[ReviewData]:
        """Parse individual ULTA review element."""
        try:
            # Extract reviewer name
            reviewer_selectors = [
                ".review-author",
                ".reviewer-name",
                ".author-name",
            ]
            reviewer_name = "Anonymous"
            for selector in reviewer_selectors:
                reviewer_elem = element.select_one(selector)
                if reviewer_elem:
                    reviewer_name = sanitize_text(reviewer_elem.get_text())
                    break

            # Extract rating
            rating = 0.0
            rating_selectors = [
                ".star-rating",
                ".rating",
                "[data-rating]",
                ".pr-rating",
            ]
            for selector in rating_selectors:
                rating_elem = element.select_one(selector)
                if rating_elem:
                    # Try data attribute first
                    rating_attr = rating_elem.get("data-rating")
                    if rating_attr:
                        try:
                            rating = float(rating_attr)
                            break
                        except ValueError:
                            pass
                    
                    # Try to count filled stars
                    filled_stars = rating_elem.select(".star-filled, .filled")
                    if filled_stars:
                        rating = float(len(filled_stars))
                        break

            # Extract review title
            title_selectors = [
                ".review-title",
                ".review-headline",
                ".pr-review-title",
            ]
            review_title = ""
            for selector in title_selectors:
                title_elem = element.select_one(selector)
                if title_elem:
                    review_title = sanitize_text(title_elem.get_text())
                    break

            # Extract review text
            text_selectors = [
                ".review-text",
                ".review-content",
                ".pr-review-text",
                ".review-body",
            ]
            review_text = ""
            for selector in text_selectors:
                text_elem = element.select_one(selector)
                if text_elem:
                    review_text = sanitize_text(text_elem.get_text())
                    break

            # Extract review date
            date_selectors = [
                ".review-date",
                ".date",
                ".pr-review-date",
                "time",
            ]
            review_date = ""
            for selector in date_selectors:
                date_elem = element.select_one(selector)
                if date_elem:
                    review_date = sanitize_text(date_elem.get_text())
                    break

            # Skip if essential data is missing
            if not review_text or rating == 0.0:
                return None

            # Generate unique review ID
            review_id = generate_review_id(
                product_id, reviewer_name, review_text, review_date
            )

            return ReviewData(
                review_id=review_id,
                product_id=product_id,
                product_name=product_name,
                product_url=product_url,
                reviewer_name=reviewer_name,
                rating=rating,
                review_title=review_title,
                review_text=review_text,
                review_date=review_date,
                verified_purchase=False,  # ULTA doesn't always show this clearly
                helpful_votes=0,  # Not easily extractable from ULTA
                retailer=self.retailer_name,
            )

        except Exception as e:
            logger.debug(f"Error parsing ULTA review: {e}")
            return None

    def _parse_powerreview_element(
        self, element, product_id: str, product_name: str, product_url: str
    ) -> Optional[ReviewData]:
        """Parse PowerReviews element used by ULTA."""
        try:
            # PowerReviews has specific class structure
            reviewer_name = "Anonymous"
            reviewer_elem = element.select_one(".pr-review-author-name")
            if reviewer_elem:
                reviewer_name = sanitize_text(reviewer_elem.get_text())

            # Rating from PowerReviews
            rating = 0.0
            rating_elem = element.select_one(".pr-rating")
            if rating_elem:
                # Count filled stars
                filled_stars = rating_elem.select(".pr-star-v4-filled")
                rating = float(len(filled_stars))

            # Review title
            review_title = ""
            title_elem = element.select_one(".pr-review-title")
            if title_elem:
                review_title = sanitize_text(title_elem.get_text())

            # Review text
            review_text = ""
            text_elem = element.select_one(".pr-review-text")
            if text_elem:
                review_text = sanitize_text(text_elem.get_text())

            # Review date
            review_date = ""
            date_elem = element.select_one(".pr-review-date")
            if date_elem:
                review_date = sanitize_text(date_elem.get_text())

            # Skip if essential data is missing
            if not review_text or rating == 0.0:
                return None

            # Generate unique review ID
            review_id = generate_review_id(
                product_id, reviewer_name, review_text, review_date
            )

            return ReviewData(
                review_id=review_id,
                product_id=product_id,
                product_name=product_name,
                product_url=product_url,
                reviewer_name=reviewer_name,
                rating=rating,
                review_title=review_title,
                review_text=review_text,
                review_date=review_date,
                verified_purchase=False,
                helpful_votes=0,
                retailer=self.retailer_name,
            )

        except Exception as e:
            logger.debug(f"Error parsing PowerReview: {e}")
            return None

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

        if isinstance(data, dict):
            # Direct review object
            if data.get("@type") == "Review":
                review = self._create_review_from_json_ld(data, product_id, product_name, product_url)
                if review:
                    reviews.append(review)

            # Product with aggregated reviews
            elif "review" in data:
                review_data = data["review"]
                if isinstance(review_data, list):
                    for review_item in review_data:
                        review = self._create_review_from_json_ld(
                            review_item, product_id, product_name, product_url
                        )
                        if review:
                            reviews.append(review)
                elif isinstance(review_data, dict):
                    review = self._create_review_from_json_ld(
                        review_data, product_id, product_name, product_url
                    )
                    if review:
                        reviews.append(review)

        return reviews

    def _create_review_from_json_ld(
        self, review_data: Dict[Any, Any], product_id: str, product_name: str, product_url: str
    ) -> Optional[ReviewData]:
        """Create a ReviewData object from JSON-LD review data."""
        try:
            # Extract rating
            rating = 0.0
            if "reviewRating" in review_data:
                rating_data = review_data["reviewRating"]
                if isinstance(rating_data, dict) and "ratingValue" in rating_data:
                    rating = float(rating_data["ratingValue"])

            # Extract reviewer name
            reviewer_name = "Anonymous"
            if "author" in review_data:
                author_data = review_data["author"]
                if isinstance(author_data, dict) and "name" in author_data:
                    reviewer_name = str(author_data["name"])
                elif isinstance(author_data, str):
                    reviewer_name = author_data

            # Extract review text
            review_text = ""
            if "reviewBody" in review_data:
                review_text = str(review_data["reviewBody"])

            # Extract review title
            review_title = ""
            if "name" in review_data:
                review_title = str(review_data["name"])

            # Extract date
            review_date = ""
            if "datePublished" in review_data:
                review_date = str(review_data["datePublished"])

            # Skip if essential data is missing
            if not review_text or rating == 0.0:
                return None

            # Generate unique review ID
            review_id = generate_review_id(
                product_id, reviewer_name, review_text, review_date
            )

            return ReviewData(
                review_id=review_id,
                product_id=product_id,
                product_name=product_name,
                product_url=product_url,
                reviewer_name=reviewer_name,
                rating=rating,
                review_title=review_title,
                review_text=review_text,
                review_date=review_date,
                verified_purchase=False,
                helpful_votes=0,
                retailer=self.retailer_name,
            )

        except Exception as e:
            logger.debug(f"Error creating review from JSON-LD: {e}")
            return None

    def _extract_reviews_from_html(
        self, soup: BeautifulSoup, product_id: str, product_name: str, product_url: str
    ) -> List[ReviewData]:
        """Extract reviews from HTML elements."""
        reviews = []

        # Common review container selectors for ULTA
        review_selectors = [
            '.review-item',
            '.customer-review',
            '[class*="review"]',
            '.review-container',
            '.pr-review',
            '.pr-review-wrap',
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
                    logger.debug(f"Error parsing ULTA HTML review: {e}")
                    continue

        return reviews

    def _extract_ulta_reviews(
        self, soup: BeautifulSoup, product_id: str, product_name: str, product_url: str
    ) -> List[ReviewData]:
        """Extract reviews using ULTA-specific selectors."""
        reviews = []

        # ULTA-specific review patterns (PowerReviews integration)
        ulta_selectors = [
            '.pr-review-list-item',
            '.pr-review-content',
            '.power-reviews-review',
            '.ulta-review-item',
        ]

        for selector in ulta_selectors:
            containers = soup.select(selector)
            for container in containers:
                try:
                    review = self._parse_powerreview_container(
                        container, product_id, product_name, product_url
                    )
                    if review:
                        reviews.append(review)
                except Exception as e:
                    logger.debug(f"Error parsing ULTA specific review: {e}")
                    continue

        return reviews

    def _deduplicate_reviews(self, reviews: List[ReviewData]) -> List[ReviewData]:
        """Remove duplicate reviews based on review_id."""
        seen_ids = set()
        unique_reviews = []

        for review in reviews:
            if review.review_id not in seen_ids:
                seen_ids.add(review.review_id)
                unique_reviews.append(review)

        return unique_reviews
