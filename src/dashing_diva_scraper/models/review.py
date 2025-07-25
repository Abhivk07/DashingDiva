"""
Data models for the Dashing Diva review scraper.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class ReviewData:
    """
    Data structure for storing customer review information.

    This dataclass represents a standardized format for customer reviews
    scraped from various retailers, ensuring consistency across different
    data sources.
    """

    product_id: str
    product_name: str
    product_url: str
    reviewer_name: str
    rating: float
    review_title: str
    review_text: str
    review_date: str
    verified_purchase: bool
    helpful_votes: int
    retailer: str
    scraped_at: str
    review_id: str

    def __post_init__(self):
        """Validate data after initialization."""
        if not 0 <= self.rating <= 5:
            raise ValueError(f"Rating must be between 0 and 5, got {self.rating}")

        if not self.product_id:
            raise ValueError("Product ID cannot be empty")

        if not self.review_id:
            raise ValueError("Review ID cannot be empty")

    def to_dict(self) -> dict:
        """Convert the review data to a dictionary."""
        return {
            "product_id": self.product_id,
            "product_name": self.product_name,
            "product_url": self.product_url,
            "reviewer_name": self.reviewer_name,
            "rating": self.rating,
            "review_title": self.review_title,
            "review_text": self.review_text,
            "review_date": self.review_date,
            "verified_purchase": self.verified_purchase,
            "helpful_votes": self.helpful_votes,
            "retailer": self.retailer,
            "scraped_at": self.scraped_at,
            "review_id": self.review_id,
        }


@dataclass
class ScrapingResult:
    """
    Result object for scraping operations.
    """

    total_reviews: int
    new_reviews: int
    errors: int
    processing_time: float
    retailer: str
    product_url: str
    timestamp: str = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now().isoformat()


@dataclass
class ProductInfo:
    """
    Product information extracted during scraping.
    """

    product_id: str
    name: str
    url: str
    retailer: str
    category: Optional[str] = None
    brand: Optional[str] = None
    price: Optional[float] = None
    availability: Optional[str] = None
    rating_summary: Optional[dict] = None
