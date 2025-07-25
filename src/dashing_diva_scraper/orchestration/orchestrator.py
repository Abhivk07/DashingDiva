"""
Main orchestrator for the Dashing Diva review scraping system.
"""

import asyncio
import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from ..database.manager import DatabaseManager
from ..models.review import ReviewData, ScrapingResult
from ..scrapers.walmart import WalmartScraper
from ..scrapers.target import TargetScraper
from ..scrapers.ulta import UltaScraper
from ..utils.helpers import RateLimiter, batch_list, validate_url

logger = logging.getLogger(__name__)


class ReviewScrapingOrchestrator:
    """
    Main orchestrator for the review scraping process.

    Coordinates scraping operations across multiple retailers,
    manages rate limiting, error handling, and data storage.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the orchestrator.

        Args:
            config: Configuration dictionary with scraping settings
        """
        self.config = config or self._get_default_config()

        # Initialize components
        self.rate_limiter = RateLimiter(
            max_requests=self.config["rate_limit"]["max_requests"],
            time_window=self.config["rate_limit"]["time_window"],
        )

        self.db_manager = DatabaseManager(self.config["database"]["path"])

        # Initialize scrapers
        self.scrapers = {
            "walmart": WalmartScraper(self.rate_limiter),
            "target": TargetScraper(self.rate_limiter),
            "ulta": UltaScraper(self.rate_limiter),
        }

        logger.info("Review scraping orchestrator initialized")

    def _get_default_config(self) -> Dict[str, Any]:
        """Get default configuration settings."""
        return {
            "rate_limit": {"max_requests": 10, "time_window": 60},
            "database": {"path": "data/reviews.db"},
            "scraping": {"max_retries": 3, "batch_size": 5, "concurrent_limit": 3},
            "target_products": [
                # Example URLs - would be replaced with actual Dashing Diva products
                "https://www.walmart.com/ip/example-dashing-diva-product-1",
                "https://www.walmart.com/ip/example-dashing-diva-product-2",
            ],
        }

    async def scrape_all_products(self, product_urls: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Scrape reviews for all configured products.

        Args:
            product_urls: Optional list of product URLs to scrape

        Returns:
            Dictionary with scraping results and statistics
        """
        if product_urls is None:
            product_urls = self.config["target_products"]

        if not product_urls:
            logger.warning("No product URLs provided for scraping")
            return {"total_scraped": 0, "errors": 0, "results": []}

        start_time = time.time()
        results = {
            "total_scraped": 0,
            "total_new_reviews": 0,
            "errors": 0,
            "results": [],
            "processing_time": 0,
        }

        # Process URLs in batches to avoid overwhelming servers
        batch_size = self.config["scraping"]["batch_size"]
        batches = list(batch_list(product_urls, batch_size))

        logger.info(f"Processing {len(product_urls)} URLs in {len(batches)} batches")

        for i, batch in enumerate(batches):
            logger.info(f"Processing batch {i + 1}/{len(batches)}")

            # Process batch concurrently with limited concurrency
            semaphore = asyncio.Semaphore(self.config["scraping"]["concurrent_limit"])
            tasks = [self._scrape_single_product_with_semaphore(url, semaphore) for url in batch]

            batch_results = await asyncio.gather(*tasks, return_exceptions=True)

            # Process batch results
            for url, result in zip(batch, batch_results):
                if isinstance(result, Exception):
                    logger.error(f"Error processing {url}: {result}")
                    results["errors"] += 1
                else:
                    results["results"].append(result)
                    results["total_scraped"] += result.total_reviews
                    results["total_new_reviews"] += result.new_reviews

                    # Save scraping result to database
                    self.db_manager.save_scraping_result(result)

        results["processing_time"] = time.time() - start_time

        logger.info(
            f"Scraping completed. Total reviews: {results['total_scraped']}, "
            f"New reviews: {results['total_new_reviews']}, "
            f"Errors: {results['errors']}, "
            f"Time: {results['processing_time']:.2f}s"
        )

        return results

    async def _scrape_single_product_with_semaphore(
        self, url: str, semaphore: asyncio.Semaphore
    ) -> ScrapingResult:
        """Scrape a single product with concurrency limiting."""
        async with semaphore:
            return await self.scrape_single_product(url)

    async def scrape_single_product(self, product_url: str) -> ScrapingResult:
        """
        Scrape reviews for a single product.

        Args:
            product_url: URL of the product to scrape

        Returns:
            ScrapingResult with operation details
        """
        start_time = time.time()

        # Validate URL
        if not validate_url(product_url):
            logger.error(f"Invalid or unsupported URL: {product_url}")
            return ScrapingResult(
                total_reviews=0,
                new_reviews=0,
                errors=1,
                processing_time=time.time() - start_time,
                retailer="Unknown",
                product_url=product_url,
            )

        # Identify retailer and get appropriate scraper
        retailer = self._identify_retailer(product_url)
        scraper = self.scrapers.get(retailer)

        if not scraper:
            logger.error(f"No scraper available for retailer: {retailer}")
            return ScrapingResult(
                total_reviews=0,
                new_reviews=0,
                errors=1,
                processing_time=time.time() - start_time,
                retailer=retailer,
                product_url=product_url,
            )

        try:
            # Perform scraping
            async with scraper:
                reviews = await scraper.scrape_product_reviews(product_url)

                # Save reviews to database
                new_reviews_count = 0
                if reviews:
                    new_reviews_count = self.db_manager.save_reviews(reviews)

                processing_time = time.time() - start_time

                logger.info(
                    f"Successfully scraped {len(reviews)} reviews from {product_url} "
                    f"({new_reviews_count} new) in {processing_time:.2f}s"
                )

                return ScrapingResult(
                    total_reviews=len(reviews),
                    new_reviews=new_reviews_count,
                    errors=0,
                    processing_time=processing_time,
                    retailer=retailer,
                    product_url=product_url,
                )

        except Exception as e:
            processing_time = time.time() - start_time
            logger.error(f"Error scraping {product_url}: {e}")

            return ScrapingResult(
                total_reviews=0,
                new_reviews=0,
                errors=1,
                processing_time=processing_time,
                retailer=retailer,
                product_url=product_url,
            )

    def _identify_retailer(self, url: str) -> str:
        """
        Identify retailer from URL.

        Args:
            url: Product URL

        Returns:
            Retailer identifier string
        """
        try:
            domain = urlparse(url).netloc.lower()

            if "walmart" in domain:
                return "walmart"
            elif "target" in domain:
                return "target"
            elif "ulta" in domain:
                return "ulta"
            else:
                return "unknown"

        except Exception:
            return "unknown"

    def get_scraping_statistics(self) -> Dict[str, Any]:
        """Get comprehensive scraping statistics."""
        db_stats = self.db_manager.get_statistics()

        return {
            "database_stats": db_stats,
            "configured_retailers": list(self.scrapers.keys()),
            "rate_limit_config": self.config["rate_limit"],
            "target_products_count": len(self.config["target_products"]),
        }

    def export_reviews(self, output_file: str = "exports/reviews_export.json") -> int:
        """
        Export all reviews to file.

        Args:
            output_file: Path to output file

        Returns:
            Number of reviews exported
        """
        return self.db_manager.export_to_json(output_file)

    def add_retailer_scraper(self, retailer_name: str, scraper_class):
        """
        Add a new retailer scraper.

        Args:
            retailer_name: Name identifier for the retailer
            scraper_class: Scraper class that inherits from BaseRetailerScraper
        """
        self.scrapers[retailer_name] = scraper_class(self.rate_limiter)
        logger.info(f"Added scraper for retailer: {retailer_name}")

    def update_config(self, new_config: Dict[str, Any]):
        """
        Update configuration settings.

        Args:
            new_config: Dictionary with new configuration values
        """
        self.config.update(new_config)

        # Update rate limiter if configuration changed
        if "rate_limit" in new_config:
            self.rate_limiter = RateLimiter(
                max_requests=self.config["rate_limit"]["max_requests"],
                time_window=self.config["rate_limit"]["time_window"],
            )

        logger.info("Configuration updated successfully")

    async def health_check(self) -> Dict[str, bool]:
        """
        Perform health check on all components.

        Returns:
            Dictionary with health status of each component
        """
        health_status = {}

        # Check database
        try:
            stats = self.db_manager.get_statistics()
            health_status["database"] = True
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            health_status["database"] = False

        # Check scrapers
        for retailer, scraper in self.scrapers.items():
            try:
                # Simple validation check
                test_url = f"https://www.{scraper.get_domain()}/test"
                is_valid = scraper.validate_url(test_url)
                health_status[f"scraper_{retailer}"] = is_valid
            except Exception as e:
                logger.error(f"Scraper {retailer} health check failed: {e}")
                health_status[f"scraper_{retailer}"] = False

        return health_status


async def main():
    """Main execution function"""
    import json
    
    # Load configuration
    config_path = "/home/lumasia/DashigDiva_workflow/config/config.json"
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
    except FileNotFoundError:
        logger.error(f"Configuration file not found: {config_path}")
        return
    
    # Initialize orchestrator
    orchestrator = ReviewScrapingOrchestrator()
    
    # Get URLs from config
    urls = config.get('target_products', [])
    if not urls:
        logger.error("No URLs found in configuration")
        return
    
    logger.info(f"Starting scraping for {len(urls)} URLs...")
    
    # Run scraping
    results = await orchestrator.run_all_scrapers(urls)
    
    # Print summary
    total_reviews = sum(len(result.reviews) for result in results)
    successful_scrapes = sum(1 for result in results if result.success)
    
    print(f"\n=== Scraping Complete ===")
    print(f"URLs processed: {len(results)}")
    print(f"Successful scrapes: {successful_scrapes}")
    print(f"Total reviews collected: {total_reviews}")
    
    for result in results:
        status = "✅" if result.success else "❌"
        print(f"{status} {result.url}: {len(result.reviews)} reviews")
        if not result.success and result.error:
            print(f"   Error: {result.error}")


if __name__ == "__main__":
    asyncio.run(main())
