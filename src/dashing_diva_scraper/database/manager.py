"""
Database management for the Dashing Diva review scraper.
"""

import json
import logging
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..models.review import ReviewData, ScrapingResult

logger = logging.getLogger(__name__)


class DatabaseManager:
    """
    Handles all database operations for storing scraped review data.

    Features:
    - SQLite database with proper schema
    - Duplicate prevention using unique review IDs
    - Efficient indexing for common queries
    - Connection pooling and error handling
    - Data export capabilities
    """

    def __init__(self, db_path: str = "data/reviews.db"):
        """
        Initialize the database manager.

        Args:
            db_path: Path to the SQLite database file
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_database()

    def _init_database(self):
        """Initialize the database with required tables and indexes."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Create reviews table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS reviews (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_id TEXT NOT NULL,
                    product_name TEXT NOT NULL,
                    product_url TEXT NOT NULL,
                    reviewer_name TEXT,
                    rating REAL NOT NULL,
                    review_title TEXT,
                    review_text TEXT,
                    review_date TEXT,
                    verified_purchase BOOLEAN,
                    helpful_votes INTEGER DEFAULT 0,
                    retailer TEXT NOT NULL,
                    scraped_at TEXT NOT NULL,
                    review_id TEXT UNIQUE NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """
            )

            # Create scraping results table for monitoring
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS scraping_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    retailer TEXT NOT NULL,
                    product_url TEXT NOT NULL,
                    total_reviews INTEGER,
                    new_reviews INTEGER,
                    errors INTEGER,
                    processing_time REAL,
                    timestamp TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """
            )

            # Create indexes for efficient querying
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_product_id ON reviews(product_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_retailer ON reviews(retailer)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_review_id ON reviews(review_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_scraped_at ON reviews(scraped_at)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_rating ON reviews(rating)")

            conn.commit()
            logger.info("Database initialized successfully")

    @contextmanager
    def _get_connection(self):
        """Context manager for database connections."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # Enable dict-like access
        try:
            yield conn
        except Exception as e:
            conn.rollback()
            logger.error(f"Database error: {e}")
            raise
        finally:
            conn.close()

    def save_reviews(self, reviews: List[ReviewData]) -> int:
        """
        Save reviews to database with duplicate prevention.

        Args:
            reviews: List of ReviewData objects to save

        Returns:
            Number of new reviews saved (excludes duplicates)
        """
        if not reviews:
            return 0

        with self._get_connection() as conn:
            cursor = conn.cursor()
            saved_count = 0

            for review in reviews:
                try:
                    cursor.execute(
                        """
                        INSERT OR IGNORE INTO reviews 
                        (product_id, product_name, product_url, reviewer_name, rating, 
                         review_title, review_text, review_date, verified_purchase, 
                         helpful_votes, retailer, scraped_at, review_id)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                        (
                            review.product_id,
                            review.product_name,
                            review.product_url,
                            review.reviewer_name,
                            review.rating,
                            review.review_title,
                            review.review_text,
                            review.review_date,
                            review.verified_purchase,
                            review.helpful_votes,
                            review.retailer,
                            review.scraped_at,
                            review.review_id,
                        ),
                    )

                    if cursor.rowcount > 0:
                        saved_count += 1

                except sqlite3.Error as e:
                    logger.error(f"Error saving review {review.review_id}: {e}")
                    continue

            conn.commit()
            logger.info(f"Saved {saved_count} new reviews out of {len(reviews)} total")
            return saved_count

    def save_scraping_result(self, result: ScrapingResult):
        """Save scraping operation results for monitoring."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO scraping_results 
                (retailer, product_url, total_reviews, new_reviews, errors, processing_time, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    result.retailer,
                    result.product_url,
                    result.total_reviews,
                    result.new_reviews,
                    result.errors,
                    result.processing_time,
                    result.timestamp,
                ),
            )
            conn.commit()

    def get_reviews(
        self,
        retailer: Optional[str] = None,
        product_id: Optional[str] = None,
        rating_min: Optional[float] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve reviews with optional filtering.

        Args:
            retailer: Filter by retailer name
            product_id: Filter by product ID
            rating_min: Minimum rating filter
            limit: Maximum number of results

        Returns:
            List of review dictionaries
        """
        query = "SELECT * FROM reviews WHERE 1=1"
        params = []

        if retailer:
            query += " AND retailer = ?"
            params.append(retailer)

        if product_id:
            query += " AND product_id = ?"
            params.append(product_id)

        if rating_min is not None:
            query += " AND rating >= ?"
            params.append(rating_min)

        query += " ORDER BY created_at DESC"

        if limit:
            query += " LIMIT ?"
            params.append(limit)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    def get_statistics(self) -> Dict[str, Any]:
        """Get database statistics for monitoring."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Total reviews
            cursor.execute("SELECT COUNT(*) FROM reviews")
            total_reviews = cursor.fetchone()[0]

            # Reviews by retailer
            cursor.execute("SELECT retailer, COUNT(*) FROM reviews GROUP BY retailer")
            by_retailer = dict(cursor.fetchall())

            # Reviews by rating
            cursor.execute("SELECT rating, COUNT(*) FROM reviews GROUP BY rating ORDER BY rating")
            by_rating = dict(cursor.fetchall())

            # Recent activity (last 24 hours)
            cursor.execute(
                """
                SELECT COUNT(*) FROM reviews 
                WHERE datetime(created_at) >= datetime('now', '-1 day')
            """
            )
            recent_reviews = cursor.fetchone()[0]

            return {
                "total_reviews": total_reviews,
                "by_retailer": by_retailer,
                "by_rating": by_rating,
                "recent_reviews_24h": recent_reviews,
            }

    def get_reviews_filtered(
        self,
        retailer: str = None,
        product_id: str = None,
        product_name: str = None,
        rating_min: float = None,
        rating_max: float = None,
        date_from: str = None,
        date_to: str = None,
        verified_only: bool = None,
        search_text: str = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Get reviews with advanced filtering options.
        
        Args:
            retailer: Filter by retailer name
            product_id: Filter by product ID
            product_name: Filter by product name (partial match)
            rating_min: Minimum rating filter
            rating_max: Maximum rating filter
            date_from: Start date filter (YYYY-MM-DD)
            date_to: End date filter (YYYY-MM-DD)
            verified_only: Show only verified purchases
            search_text: Search in review text and title
            sort_by: Column to sort by
            sort_order: Sort order (asc/desc)
            limit: Maximum number of results
            offset: Offset for pagination
            
        Returns:
            List of filtered review dictionaries
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Build dynamic query
            query = "SELECT * FROM reviews WHERE 1=1"
            params = []
            
            if retailer:
                query += " AND retailer = ?"
                params.append(retailer)
                
            if product_id:
                query += " AND product_id = ?"
                params.append(product_id)
                
            if product_name:
                query += " AND product_name LIKE ?"
                params.append(f"%{product_name}%")
                
            if rating_min is not None:
                query += " AND rating >= ?"
                params.append(rating_min)
                
            if rating_max is not None:
                query += " AND rating <= ?"
                params.append(rating_max)
                
            if date_from:
                query += " AND date(created_at) >= ?"
                params.append(date_from)
                
            if date_to:
                query += " AND date(created_at) <= ?"
                params.append(date_to)
                
            if verified_only:
                query += " AND verified_purchase = 1"
                
            if search_text:
                query += " AND (review_text LIKE ? OR review_title LIKE ?)"
                params.extend([f"%{search_text}%", f"%{search_text}%"])
            
            # Add sorting
            if sort_by in ["created_at", "rating", "review_date", "helpful_votes", "retailer"]:
                order = "ASC" if sort_order.lower() == "asc" else "DESC"
                query += f" ORDER BY {sort_by} {order}"
            
            # Add pagination
            query += " LIMIT ? OFFSET ?"
            params.extend([limit, offset])
            
            cursor.execute(query, params)
            columns = [desc[0] for desc in cursor.description]
            
            return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def get_unique_retailers(self) -> List[str]:
        """Get list of unique retailers."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT retailer FROM reviews ORDER BY retailer")
            return [row[0] for row in cursor.fetchall()]

    def get_unique_products(self) -> List[Dict[str, str]]:
        """Get list of unique products."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT DISTINCT product_id, product_name, retailer 
                FROM reviews 
                ORDER BY product_name
            """)
            return [
                {"id": row[0], "name": row[1], "retailer": row[2]} 
                for row in cursor.fetchall()
            ]

    def get_rating_range(self) -> Dict[str, float]:
        """Get min and max ratings available."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT MIN(rating), MAX(rating) FROM reviews")
            result = cursor.fetchone()
            return {
                "min": result[0] if result[0] is not None else 0.0,
                "max": result[1] if result[1] is not None else 5.0
            }

    def get_date_range(self) -> Dict[str, str]:
        """Get date range of reviews."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT MIN(date(created_at)), MAX(date(created_at)) FROM reviews")
            result = cursor.fetchone()
            return {
                "min": result[0] if result[0] is not None else "",
                "max": result[1] if result[1] is not None else ""
            }

    def export_to_json(self, output_file: str = "exports/reviews_export.json") -> int:
        """
        Export all reviews to JSON file.

        Args:
            output_file: Path to output JSON file

        Returns:
            Number of reviews exported
        """
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        reviews = self.get_reviews()

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(reviews, f, indent=2, ensure_ascii=False, default=str)

        logger.info(f"Exported {len(reviews)} reviews to {output_file}")
        return len(reviews)

    def cleanup_old_data(self, days: int = 90):
        """Remove data older than specified days."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Clean old scraping results
            cursor.execute(
                """
                DELETE FROM scraping_results 
                WHERE datetime(created_at) < datetime('now', '-{} days')
            """.format(
                    days
                )
            )

            deleted_results = cursor.rowcount
            conn.commit()

            logger.info(f"Cleaned up {deleted_results} old scraping results")
            return deleted_results
