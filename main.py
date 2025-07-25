#!/usr/bin/env python3
"""
Dashing Diva Review Scraper - Main Entry Point

A production-ready web scraper for collecting customer reviews from major retailers.
"""

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List

# Add src directory to Python path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from dashing_diva_scraper import DatabaseManager, ReviewScrapingOrchestrator
from dashing_diva_scraper.web import create_app

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("logs/scraper.log"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


def load_config(config_path: str = "config/config.json") -> Dict[str, Any]:
    """Load configuration from file."""
    config_file = Path(config_path)

    if config_file.exists():
        with open(config_file, "r") as f:
            return json.load(f)
    else:
        logger.warning(f"Config file {config_path} not found, using defaults")
        return {}


async def run_scraper(urls: List[str], config: Dict[str, Any]):
    """Run the scraper for specified URLs."""
    logger.info("Starting Dashing Diva Review Scraper")

    orchestrator = ReviewScrapingOrchestrator(config)

    try:
        # Run health check first
        health_status = await orchestrator.health_check()
        logger.info(f"Health check results: {health_status}")

        # Scrape reviews
        results = await orchestrator.scrape_all_products(urls)

        # Print results
        logger.info(f"Scraping completed successfully!")
        logger.info(f"Total reviews scraped: {results['total_scraped']}")
        logger.info(f"New reviews saved: {results['total_new_reviews']}")
        logger.info(f"Errors encountered: {results['errors']}")
        logger.info(f"Processing time: {results['processing_time']:.2f} seconds")

        # Export results
        export_file = f"exports/scrape_results_{int(asyncio.get_event_loop().time())}.json"
        count = orchestrator.export_reviews(export_file)
        logger.info(f"Exported {count} reviews to {export_file}")

        return results

    except Exception as e:
        logger.error(f"Error during scraping: {e}")
        raise


def run_dashboard(config: Dict[str, Any], host: str = "0.0.0.0", port: int = 5000):
    """Run the web dashboard."""
    logger.info("Starting Dashing Diva Review Dashboard")

    app = create_app(config)
    app.run(host=host, port=port, debug=config.get("debug", False))


def show_stats(config: Dict[str, Any]):
    """Show database statistics."""
    db_manager = DatabaseManager(config.get("database", {}).get("path", "data/reviews.db"))

    stats = db_manager.get_statistics()

    print("\n=== Dashing Diva Review Scraper Statistics ===")
    print(f"Total Reviews: {stats['total_reviews']}")
    print(f"Recent Reviews (24h): {stats['recent_reviews_24h']}")

    print("\nBy Retailer:")
    for retailer, count in stats["by_retailer"].items():
        print(f"  {retailer}: {count}")

    print("\nBy Rating:")
    for rating, count in sorted(stats["by_rating"].items()):
        print(f"  {rating} stars: {count}")


def create_sample_config():
    """Create a sample configuration file."""
    sample_config = {
        "rate_limit": {"max_requests": 10, "time_window": 60},
        "database": {"path": "data/reviews.db"},
        "scraping": {"max_retries": 3, "batch_size": 5, "concurrent_limit": 3},
        "target_products": [
            "https://www.walmart.com/ip/dashing-diva-example-product-1",
            "https://www.walmart.com/ip/dashing-diva-example-product-2",
        ],
        "flask": {"SECRET_KEY": "change-this-in-production", "DEBUG": False},
        "logging": {"level": "INFO", "file": "logs/scraper.log"},
    }

    config_dir = Path("config")
    config_dir.mkdir(exist_ok=True)

    config_file = config_dir / "config.json"
    with open(config_file, "w") as f:
        json.dump(sample_config, f, indent=2)

    print(f"Sample configuration created at {config_file}")
    print("Please edit this file with your actual product URLs and settings.")


def main():
    """Main CLI interface."""
    parser = argparse.ArgumentParser(
        description="Dashing Diva Review Scraper",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run scraper with default config
  python3 main.py scrape

  # Run scraper with specific URLs
  python3 main.py scrape --urls https://www.walmart.com/ip/product/123

  # Start web dashboard
  python3 main.py dashboard

  # Show statistics
  python3 main.py stats

  # Create sample configuration
  python3 main.py init-config
        """,
    )

    parser.add_argument(
        "--config",
        default="config/config.json",
        help="Path to configuration file (default: config/config.json)",
    )

    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Scrape command
    scrape_parser = subparsers.add_parser("scrape", help="Run the review scraper")
    scrape_parser.add_argument(
        "--urls", nargs="+", help="Product URLs to scrape (overrides config file)"
    )

    # Dashboard command
    dashboard_parser = subparsers.add_parser("dashboard", help="Start web dashboard")
    dashboard_parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    dashboard_parser.add_argument("--port", type=int, default=5000, help="Port to bind to")

    # Stats command
    subparsers.add_parser("stats", help="Show database statistics")

    # Init config command
    subparsers.add_parser("init-config", help="Create sample configuration file")

    args = parser.parse_args()

    # Set logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Ensure required directories exist
    Path("data").mkdir(exist_ok=True)
    Path("logs").mkdir(exist_ok=True)
    Path("exports").mkdir(exist_ok=True)

    # Load configuration
    config = load_config(args.config)

    try:
        if args.command == "scrape":
            urls = args.urls or config.get("target_products", [])
            if not urls:
                print(
                    "Error: No URLs specified. Use --urls or configure target_products in config file."
                )
                print("Run 'python3 main.py init-config' to create a sample configuration.")
                sys.exit(1)

            results = asyncio.run(run_scraper(urls, config))

        elif args.command == "dashboard":
            run_dashboard(config, args.host, args.port)

        elif args.command == "stats":
            show_stats(config)

        elif args.command == "init-config":
            create_sample_config()

        else:
            parser.print_help()

    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
