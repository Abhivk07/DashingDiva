"""
Unit tests for the Dashing Diva review scraper.
"""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.dashing_diva_scraper.database.manager import DatabaseManager
from src.dashing_diva_scraper.models.review import ReviewData, ScrapingResult
from src.dashing_diva_scraper.scrapers.walmart import WalmartScraper
from src.dashing_diva_scraper.utils.helpers import (
    RateLimiter,
    generate_review_id,
    sanitize_text,
    validate_url,
)


class TestReviewData:
    """Test cases for ReviewData model."""

    def test_review_data_creation(self):
        """Test creating a valid ReviewData instance."""
        review = ReviewData(
            product_id="12345",
            product_name="Test Product",
            product_url="https://example.com/product/12345",
            reviewer_name="John Doe",
            rating=4.5,
            review_title="Great product!",
            review_text="I really love this product.",
            review_date="2024-01-15",
            verified_purchase=True,
            helpful_votes=5,
            retailer="Walmart",
            scraped_at="2024-01-15T10:00:00",
            review_id="abc123",
        )

        assert review.product_id == "12345"
        assert review.rating == 4.5
        assert review.verified_purchase is True

    def test_review_data_invalid_rating(self):
        """Test that invalid ratings raise ValueError."""
        with pytest.raises(ValueError, match="Rating must be between 0 and 5"):
            ReviewData(
                product_id="12345",
                product_name="Test Product",
                product_url="https://example.com",
                reviewer_name="John Doe",
                rating=6.0,  # Invalid rating
                review_title="Title",
                review_text="Text",
                review_date="2024-01-15",
                verified_purchase=True,
                helpful_votes=0,
                retailer="Walmart",
                scraped_at="2024-01-15T10:00:00",
                review_id="abc123",
            )

    def test_review_data_to_dict(self):
        """Test converting ReviewData to dictionary."""
        review = ReviewData(
            product_id="12345",
            product_name="Test Product",
            product_url="https://example.com",
            reviewer_name="John Doe",
            rating=4.0,
            review_title="Title",
            review_text="Text",
            review_date="2024-01-15",
            verified_purchase=True,
            helpful_votes=0,
            retailer="Walmart",
            scraped_at="2024-01-15T10:00:00",
            review_id="abc123",
        )

        result = review.to_dict()
        assert isinstance(result, dict)
        assert result["product_id"] == "12345"
        assert result["rating"] == 4.0


class TestUtilityFunctions:
    """Test cases for utility functions."""

    def test_generate_review_id(self):
        """Test review ID generation."""
        product_id = "12345"
        reviewer_name = "John Doe"
        review_text = "Great product!"

        review_id = generate_review_id(product_id, reviewer_name, review_text)

        assert isinstance(review_id, str)
        assert len(review_id) == 32  # MD5 hash length

        # Same inputs should generate same ID
        review_id2 = generate_review_id(product_id, reviewer_name, review_text)
        assert review_id == review_id2

        # Different inputs should generate different IDs
        review_id3 = generate_review_id(product_id, "Jane Doe", review_text)
        assert review_id != review_id3

    def test_validate_url(self):
        """Test URL validation."""
        valid_urls = [
            "https://www.walmart.com/ip/product/12345",
            "https://www.target.com/p/product-name/-/A-12345",
            "https://www.ulta.com/product/12345",
        ]

        invalid_urls = [
            "https://www.amazon.com/product/12345",
            "https://www.google.com",
            "not-a-url",
            "",
        ]

        for url in valid_urls:
            assert validate_url(url) is True

        for url in invalid_urls:
            assert validate_url(url) is False

    def test_sanitize_text(self):
        """Test text sanitization."""
        test_cases = [
            ("  Multiple   spaces  ", "Multiple spaces"),
            ("Text with\r\nnewlines", "Text with\nnewlines"),
            ("Text with\x00null bytes", "Text withnull bytes"),
            ("", ""),
            (None, ""),
        ]

        for input_text, expected in test_cases:
            result = sanitize_text(input_text)
            assert result == expected


class TestRateLimiter:
    """Test cases for rate limiting functionality."""

    @pytest.mark.asyncio
    async def test_rate_limiter_basic(self):
        """Test basic rate limiting functionality."""
        limiter = RateLimiter(max_requests=2, time_window=1)

        # First two requests should be immediate
        start_time = asyncio.get_event_loop().time()
        await limiter.wait_if_needed()
        await limiter.wait_if_needed()
        elapsed = asyncio.get_event_loop().time() - start_time

        assert elapsed < 0.1  # Should be nearly instantaneous

        # Third request should be delayed
        start_time = asyncio.get_event_loop().time()
        await limiter.wait_if_needed()
        elapsed = asyncio.get_event_loop().time() - start_time

        assert elapsed >= 0.9  # Should wait for time window


class TestWalmartScraper:
    """Test cases for Walmart scraper."""

    def test_extract_product_id(self):
        """Test product ID extraction from Walmart URLs."""
        scraper = WalmartScraper(Mock())

        test_cases = [
            ("https://www.walmart.com/ip/product-name/12345", "12345"),
            ("https://www.walmart.com/ip/product-name/12345?param=value", "12345"),
            ("https://www.walmart.com/ip/another-product/98765", "98765"),
        ]

        for url, expected_id in test_cases:
            result = scraper.extract_product_id(url)
            assert result == expected_id

    def test_get_domain(self):
        """Test domain getter."""
        scraper = WalmartScraper(Mock())
        assert scraper.get_domain() == "walmart.com"

    def test_validate_url(self):
        """Test URL validation for Walmart."""
        scraper = WalmartScraper(Mock())

        valid_urls = [
            "https://www.walmart.com/ip/product/12345",
            "https://walmart.com/ip/product/12345",
        ]

        invalid_urls = [
            "https://www.target.com/p/product/12345",
            "https://www.example.com/product/12345",
        ]

        for url in valid_urls:
            assert scraper.validate_url(url) is True

        for url in invalid_urls:
            assert scraper.validate_url(url) is False


class TestDatabaseManager:
    """Test cases for database management."""

    def test_database_initialization(self, tmp_path):
        """Test database initialization."""
        db_path = tmp_path / "test_reviews.db"
        db_manager = DatabaseManager(str(db_path))

        assert db_path.exists()

        # Test that tables were created
        import sqlite3

        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]

        assert "reviews" in tables
        assert "scraping_results" in tables

        conn.close()

    def test_save_reviews(self, tmp_path):
        """Test saving reviews to database."""
        db_path = tmp_path / "test_reviews.db"
        db_manager = DatabaseManager(str(db_path))

        # Create test reviews
        reviews = [
            ReviewData(
                product_id="12345",
                product_name="Test Product",
                product_url="https://example.com",
                reviewer_name="John Doe",
                rating=4.0,
                review_title="Great!",
                review_text="Love it",
                review_date="2024-01-15",
                verified_purchase=True,
                helpful_votes=5,
                retailer="Walmart",
                scraped_at="2024-01-15T10:00:00",
                review_id="unique123",
            ),
            ReviewData(
                product_id="12346",
                product_name="Another Product",
                product_url="https://example.com",
                reviewer_name="Jane Doe",
                rating=5.0,
                review_title="Excellent!",
                review_text="Perfect",
                review_date="2024-01-16",
                verified_purchase=True,
                helpful_votes=3,
                retailer="Walmart",
                scraped_at="2024-01-16T10:00:00",
                review_id="unique456",
            ),
        ]

        # Save reviews
        saved_count = db_manager.save_reviews(reviews)
        assert saved_count == 2

        # Try to save same reviews again (should be ignored due to unique constraint)
        saved_count = db_manager.save_reviews(reviews)
        assert saved_count == 0

    def test_get_reviews(self, tmp_path):
        """Test retrieving reviews from database."""
        db_path = tmp_path / "test_reviews.db"
        db_manager = DatabaseManager(str(db_path))

        # Save test review
        review = ReviewData(
            product_id="12345",
            product_name="Test Product",
            product_url="https://example.com",
            reviewer_name="John Doe",
            rating=4.0,
            review_title="Great!",
            review_text="Love it",
            review_date="2024-01-15",
            verified_purchase=True,
            helpful_votes=5,
            retailer="Walmart",
            scraped_at="2024-01-15T10:00:00",
            review_id="unique123",
        )

        db_manager.save_reviews([review])

        # Test retrieval
        reviews = db_manager.get_reviews()
        assert len(reviews) == 1
        assert reviews[0]["product_id"] == "12345"

        # Test filtering
        walmart_reviews = db_manager.get_reviews(retailer="Walmart")
        assert len(walmart_reviews) == 1

        target_reviews = db_manager.get_reviews(retailer="Target")
        assert len(target_reviews) == 0


if __name__ == "__main__":
    pytest.main([__file__])
