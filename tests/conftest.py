"""Test configuration and fixtures."""

import shutil
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def temp_dir():
    """Create a temporary directory for tests."""
    temp_path = Path(tempfile.mkdtemp())
    yield temp_path
    shutil.rmtree(temp_path)


@pytest.fixture
def sample_config():
    """Provide sample configuration for tests."""
    return {
        "rate_limit": {"max_requests": 10, "time_window": 60},
        "database": {"path": "data/test_reviews.db"},
        "scraping": {"max_retries": 3, "batch_size": 5, "concurrent_limit": 3},
        "target_products": [
            "https://www.walmart.com/ip/test-product-1/111",
            "https://www.walmart.com/ip/test-product-2/222",
        ],
    }


@pytest.fixture
def sample_review_data():
    """Provide sample review data for tests."""
    from src.dashing_diva_scraper.models.review import ReviewData

    return ReviewData(
        product_id="test123",
        product_name="Test Product",
        product_url="https://www.walmart.com/ip/test/123",
        reviewer_name="Test Reviewer",
        rating=4.5,
        review_title="Great product",
        review_text="This is a test review text.",
        review_date="2024-01-15",
        verified_purchase=True,
        helpful_votes=3,
        retailer="Walmart",
        scraped_at="2024-01-15T10:00:00",
        review_id="test_review_123",
    )
