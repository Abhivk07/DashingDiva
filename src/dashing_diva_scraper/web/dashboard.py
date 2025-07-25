"""
Web dashboard for monitoring and visualizing review scraping data.
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List

from flask import Flask, jsonify, render_template, request

from ..database.manager import DatabaseManager
from ..orchestration.orchestrator import ReviewScrapingOrchestrator

logger = logging.getLogger(__name__)


class ReviewDashboard:
    """
    Flask-based web dashboard for monitoring review scraping operations.

    Provides real-time insights into:
    - Scraping statistics and performance
    - Review data visualization
    - System health monitoring
    - Manual scraping triggers
    """

    def __init__(self, config: Dict[str, Any] = None):
        """Initialize the dashboard."""
        self.config = config or self._get_default_config()
        self.app = Flask(__name__)
        self.app.config.update(self.config["flask"])

        # Initialize components
        self.db_manager = DatabaseManager(self.config["database"]["path"])
        self.orchestrator = ReviewScrapingOrchestrator(self.config)

        # Register routes
        self._register_routes()

        logger.info("Review dashboard initialized")

    def _get_default_config(self) -> Dict[str, Any]:
        """Get default dashboard configuration."""
        return {
            "flask": {"SECRET_KEY": "dev-secret-key-change-in-production", "DEBUG": True},
            "database": {"path": "data/reviews.db"},
            "rate_limit": {"max_requests": 10, "time_window": 60},
        }

    def _register_routes(self):
        """Register Flask routes."""

        @self.app.route("/")
        def dashboard():
            """Main dashboard page."""
            try:
                stats = self._get_dashboard_stats()
                recent_reviews = stats["recent_reviews"]
                return render_template("dashboard.html", stats=stats, recent_reviews=recent_reviews)
            except Exception as e:
                logger.error(f"Error loading dashboard: {e}")
                return f"Error loading dashboard: {e}", 500        @self.app.route("/api/stats")
        def api_stats():
            """API endpoint for dashboard statistics."""
            try:
                stats = self._get_dashboard_stats()
                return jsonify(stats)
            except Exception as e:
                logger.error(f"Error getting stats: {e}")
                return jsonify({"error": str(e)}), 500

        @self.app.route("/api/reviews")
        def api_reviews():
            """API endpoint for review data with advanced filtering."""
            try:
                # Get query parameters for filtering
                retailer = request.args.get("retailer")
                product_id = request.args.get("product_id")
                product_name = request.args.get("product_name")
                rating_min = request.args.get("rating_min", type=float)
                rating_max = request.args.get("rating_max", type=float)
                date_from = request.args.get("date_from")
                date_to = request.args.get("date_to")
                verified_only = request.args.get("verified_only", type=bool)
                search_text = request.args.get("search_text")
                sort_by = request.args.get("sort_by", "created_at")
                sort_order = request.args.get("sort_order", "desc")
                limit = request.args.get("limit", 100, type=int)
                offset = request.args.get("offset", 0, type=int)

                reviews = self.db_manager.get_reviews_filtered(
                    retailer=retailer,
                    product_id=product_id,
                    product_name=product_name,
                    rating_min=rating_min,
                    rating_max=rating_max,
                    date_from=date_from,
                    date_to=date_to,
                    verified_only=verified_only,
                    search_text=search_text,
                    sort_by=sort_by,
                    sort_order=sort_order,
                    limit=limit,
                    offset=offset
                )

                return jsonify(reviews)
            except Exception as e:
                logger.error(f"Error getting reviews: {e}")
                return jsonify({"error": str(e)}), 500

        @self.app.route("/api/filters")
        def api_filters():
            """API endpoint for available filter options."""
            try:
                filters = {
                    "retailers": self.db_manager.get_unique_retailers(),
                    "products": self.db_manager.get_unique_products(),
                    "rating_range": self.db_manager.get_rating_range(),
                    "date_range": self.db_manager.get_date_range()
                }
                return jsonify(filters)
            except Exception as e:
                logger.error(f"Error getting filters: {e}")
                return jsonify({"error": str(e)}), 500

        @self.app.route("/api/health")
        def api_health():
            """Health check endpoint."""
            try:
                import asyncio

                health_status = asyncio.run(self.orchestrator.health_check())
                return jsonify(health_status)
            except Exception as e:
                logger.error(f"Health check failed: {e}")
                return jsonify({"error": str(e)}), 500

        @self.app.route("/api/scrape", methods=["POST"])
        def api_scrape():
            """Manual scraping trigger endpoint."""
            try:
                data = request.get_json()
                product_urls = data.get("urls", [])

                if not product_urls:
                    return jsonify({"error": "No URLs provided"}), 400

                # Run scraping in background (in production, use Celery or similar)
                import asyncio

                results = asyncio.run(self.orchestrator.scrape_all_products(product_urls))

                return jsonify(results)
            except Exception as e:
                logger.error(f"Error running manual scrape: {e}")
                return jsonify({"error": str(e)}), 500

        @self.app.route("/api/export")
        def api_export():
            """Export reviews endpoint."""
            try:
                output_file = request.args.get("file", "exports/manual_export.json")
                count = self.orchestrator.export_reviews(output_file)

                return jsonify(
                    {
                        "exported_count": count,
                        "file": output_file,
                        "timestamp": datetime.now().isoformat(),
                    }
                )
            except Exception as e:
                logger.error(f"Error exporting reviews: {e}")
                return jsonify({"error": str(e)}), 500

    def _get_dashboard_stats(self) -> Dict[str, Any]:
        """Get comprehensive dashboard statistics."""
        # Basic database stats
        db_stats = self.db_manager.get_statistics()

        # Recent activity
        recent_reviews = self.db_manager.get_reviews(limit=10)

        # Performance metrics
        try:
            orchestrator_stats = self.orchestrator.get_scraping_statistics()
        except Exception as e:
            logger.warning(f"Could not get orchestrator stats: {e}")
            orchestrator_stats = {}

        # Chart data for visualization
        chart_data = self._get_chart_data()

        # Calculate additional metrics
        total_reviews = db_stats["total_reviews"]
        avg_rating = 0.0
        unique_products = 0
        retailers_count = len(db_stats["by_retailer"])

        if total_reviews > 0:
            # Calculate average rating
            total_rating_points = sum(
                rating * count for rating, count in db_stats["by_rating"].items()
            )
            avg_rating = total_rating_points / total_reviews

            # Get unique products count
            try:
                with self.db_manager._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT COUNT(DISTINCT product_name) FROM reviews")
                    unique_products = cursor.fetchone()[0]
            except Exception as e:
                logger.warning(f"Could not get unique products count: {e}")
                unique_products = 0

        return {
            # Top-level stats for template compatibility
            "total_reviews": total_reviews,
            "avg_rating": avg_rating,
            "unique_products": unique_products,
            "retailers_count": retailers_count,
            "by_retailer": db_stats["by_retailer"],
            "by_rating": db_stats["by_rating"],
            "charts": chart_data,
            # Detailed breakdown
            "overview": {
                "total_reviews": total_reviews,
                "recent_reviews_24h": db_stats["recent_reviews_24h"],
                "active_retailers": retailers_count,
                "last_updated": datetime.now().isoformat(),
            },
            "recent_reviews": recent_reviews,
            "system": orchestrator_stats,
        }

    def _get_chart_data(self) -> Dict[str, Any]:
        """Generate data for dashboard charts."""
        try:
            # Get reviews from last 30 days for trending
            reviews = self.db_manager.get_reviews(limit=1000)

            # Group by date for time series
            daily_counts = {}
            rating_distribution = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}

            for review in reviews:
                # Parse date (handling various formats)
                try:
                    if "T" in review["scraped_at"]:
                        date = datetime.fromisoformat(review["scraped_at"].replace("Z", "+00:00"))
                    else:
                        date = datetime.strptime(review["scraped_at"], "%Y-%m-%d")

                    date_key = date.strftime("%Y-%m-%d")
                    daily_counts[date_key] = daily_counts.get(date_key, 0) + 1

                    # Rating distribution
                    rating = int(review["rating"])
                    if rating in rating_distribution:
                        rating_distribution[rating] += 1

                except Exception:
                    continue

            # Format for Chart.js
            dates = sorted(daily_counts.keys())[-30:]  # Last 30 days
            counts = [daily_counts.get(date, 0) for date in dates]

            return {
                "daily_reviews": {"labels": dates, "data": counts},
                "rating_distribution": {
                    "labels": list(rating_distribution.keys()),
                    "data": list(rating_distribution.values()),
                },
            }

        except Exception as e:
            logger.error(f"Error generating chart data: {e}")
            return {
                "daily_reviews": {"labels": [], "data": []},
                "rating_distribution": {"labels": [], "data": []},
            }

    def run(self, host: str = "0.0.0.0", port: int = 5000, debug: bool = False):
        """Run the Flask application."""
        logger.info(f"Starting dashboard on {host}:{port}")
        self.app.run(host=host, port=port, debug=debug)


def create_app(config: Dict[str, Any] = None) -> Flask:
    """Factory function to create Flask app."""
    dashboard = ReviewDashboard(config)
    return dashboard.app
