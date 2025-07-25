"""
Integration tests for the Dashing Diva review scraper.
"""

import asyncio
import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from src.dashing_diva_scraper.models.review import ReviewData
from src.dashing_diva_scraper.orchestration.orchestrator import ReviewScrapingOrchestrator


class TestScrapingOrchestrator:
    """Integration tests for the review scraping orchestrator."""

    def test_orchestrator_initialization(self, tmp_path):
        """Test orchestrator initialization with custom config."""
        config = {
            "rate_limit": {"max_requests": 5, "time_window": 30},
            "database": {"path": str(tmp_path / "test_reviews.db")},
            "scraping": {"max_retries": 2, "batch_size": 3, "concurrent_limit": 2},
        }

        orchestrator = ReviewScrapingOrchestrator(config)

        assert orchestrator.config["rate_limit"]["max_requests"] == 5
        assert orchestrator.config["scraping"]["batch_size"] == 3
        assert "walmart" in orchestrator.scrapers

    @pytest.mark.asyncio
    async def test_identify_retailer(self):
        """Test retailer identification from URLs."""
        orchestrator = ReviewScrapingOrchestrator()

        test_cases = [
            ("https://www.walmart.com/ip/product/12345", "walmart"),
            ("https://www.target.com/p/product/12345", "target"),
            ("https://www.ulta.com/product/12345", "ulta"),
            ("https://www.unknown.com/product/12345", "unknown"),
        ]

        for url, expected_retailer in test_cases:
            result = orchestrator._identify_retailer(url)
            assert result == expected_retailer

    @pytest.mark.asyncio
    async def test_health_check(self, tmp_path):
        """Test system health check functionality."""
        config = {"database": {"path": str(tmp_path / "test_reviews.db")}}

        orchestrator = ReviewScrapingOrchestrator(config)
        health_status = await orchestrator.health_check()

        assert isinstance(health_status, dict)
        assert "database" in health_status
        assert "scraper_walmart" in health_status
        assert health_status["database"] is True


class TestEndToEndScraping:
    """End-to-end integration tests."""

    @pytest.mark.asyncio
    async def test_mock_scraping_workflow(self, tmp_path):
        """Test complete scraping workflow with mocked HTTP responses."""

        # Mock HTML content that simulates a product page with reviews
        mock_html = """
        <html>
            <head><title>Test Product</title></head>
            <body>
                <h1 data-automation-id="product-title">Dashing Diva Test Product</h1>
                <div class="review-item">
                    <div class="reviewer-name">John Doe</div>
                    <div class="rating" aria-label="4 out of 5 stars">★★★★☆</div>
                    <div class="review-title">Great product!</div>
                    <div class="review-text">I really love this product. Highly recommended!</div>
                </div>
                <div class="review-item">
                    <div class="reviewer-name">Jane Smith</div>
                    <div class="rating" aria-label="5 out of 5 stars">★★★★★</div>
                    <div class="review-title">Excellent quality</div>
                    <div class="review-text">Amazing quality and fast shipping.</div>
                </div>
            </body>
        </html>
        """

        config = {
            "database": {"path": str(tmp_path / "test_reviews.db")},
            "rate_limit": {"max_requests": 100, "time_window": 60},
        }

        orchestrator = ReviewScrapingOrchestrator(config)

        # Mock the HTTP response
        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_response = Mock()
            mock_response.status = 200
            mock_response.text = asyncio.coroutine(lambda: mock_html)()
            mock_get.return_value.__aenter__ = asyncio.coroutine(lambda: mock_response)
            mock_get.return_value.__aexit__ = asyncio.coroutine(lambda *args: None)

            # Test scraping a single product
            test_url = "https://www.walmart.com/ip/test-product/12345"
            result = await orchestrator.scrape_single_product(test_url)

            assert result.retailer == "walmart"
            assert result.errors == 0
            assert result.product_url == test_url

    def test_configuration_management(self, tmp_path):
        """Test configuration loading and updating."""
        # Create test config file
        config_data = {
            "rate_limit": {"max_requests": 15, "time_window": 90},
            "target_products": [
                "https://www.walmart.com/ip/test1/111",
                "https://www.walmart.com/ip/test2/222",
            ],
        }

        config_file = tmp_path / "test_config.json"
        with open(config_file, "w") as f:
            json.dump(config_data, f)

        # Test loading configuration
        with open(config_file, "r") as f:
            loaded_config = json.load(f)

        orchestrator = ReviewScrapingOrchestrator(loaded_config)

        assert orchestrator.config["rate_limit"]["max_requests"] == 15
        assert len(orchestrator.config["target_products"]) == 2

        # Test updating configuration
        new_config = {"rate_limit": {"max_requests": 20, "time_window": 120}}

        orchestrator.update_config(new_config)
        assert orchestrator.config["rate_limit"]["max_requests"] == 20

    def test_data_export_functionality(self, tmp_path):
        """Test data export functionality."""
        config = {"database": {"path": str(tmp_path / "test_reviews.db")}}

        orchestrator = ReviewScrapingOrchestrator(config)

        # Add some test data
        test_reviews = [
            ReviewData(
                product_id="12345",
                product_name="Test Product",
                product_url="https://example.com",
                reviewer_name="Test User",
                rating=4.0,
                review_title="Good product",
                review_text="Works well",
                review_date="2024-01-15",
                verified_purchase=True,
                helpful_votes=2,
                retailer="Walmart",
                scraped_at="2024-01-15T10:00:00",
                review_id="test123",
            )
        ]

        orchestrator.db_manager.save_reviews(test_reviews)

        # Test export
        export_file = tmp_path / "test_export.json"
        count = orchestrator.export_reviews(str(export_file))

        assert count == 1
        assert export_file.exists()

        # Verify export content
        with open(export_file, "r") as f:
            exported_data = json.load(f)

        assert len(exported_data) == 1
        assert exported_data[0]["product_id"] == "12345"


class TestDashboardIntegration:
    """Integration tests for the web dashboard."""

    def test_dashboard_creation(self, tmp_path):
        """Test dashboard initialization."""
        config = {
            "flask": {"SECRET_KEY": "test-secret", "DEBUG": True},
            "database": {"path": str(tmp_path / "test_reviews.db")},
        }

        from src.dashing_diva_scraper.web.dashboard import ReviewDashboard

        dashboard = ReviewDashboard(config)

        assert dashboard.app is not None
        assert dashboard.config["flask"]["SECRET_KEY"] == "test-secret"

    def test_dashboard_routes(self, tmp_path):
        """Test dashboard API routes."""
        config = {
            "flask": {"SECRET_KEY": "test-secret", "TESTING": True},
            "database": {"path": str(tmp_path / "test_reviews.db")},
        }

        from src.dashing_diva_scraper.web.dashboard import create_app

        app = create_app(config)

        with app.test_client() as client:
            # Test health endpoint
            response = client.get("/api/health")
            assert response.status_code == 200

            # Test stats endpoint
            response = client.get("/api/stats")
            assert response.status_code == 200

            data = json.loads(response.data)
            assert "overview" in data


if __name__ == "__main__":
    pytest.main([__file__])
