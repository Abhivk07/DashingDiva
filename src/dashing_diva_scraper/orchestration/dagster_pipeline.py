"""
Dagster workflow orchestration for Dashing Diva Review Scraping.
Implements production-grade data pipeline with monitoring, alerting, and retry logic.
"""

import asyncio
import json
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import pandas as pd
from dagster import (
    AssetMaterialization,
    Config,
    DagsterEventType,
    DailyPartitionsDefinition,
    DefaultSensorStatus,
    ExpectationResult,
    In,
    InitResourceContext,
    MetadataValue,
    Nothing,
    OpExecutionContext,
    Out,
    RunRequest,
    SkipReason,
    StaticPartitionsDefinition,
    get_dagster_logger,
    job,
    op,
    resource,
    schedule,
    sensor,
)

from src.dashing_diva_scraper import DatabaseManager, ReviewScrapingOrchestrator


class ScrapingConfig(Config):
    """Configuration schema for scraping operations."""

    product_urls: List[str]
    max_retries: int = 3
    rate_limit_requests: int = 10
    rate_limit_window: int = 60
    output_format: str = "json"
    retailer_filter: Optional[str] = None


@resource
def scraping_orchestrator_resource(init_context: InitResourceContext):
    """Dagster resource for the review scraping orchestrator."""
    config = {
        "rate_limit": {"max_requests": 10, "time_window": 60},
        "database": {"path": "data/reviews.db"},
        "scraping": {"max_retries": 3, "batch_size": 5, "concurrent_limit": 3},
    }
    return ReviewScrapingOrchestrator(config)


@resource
def database_manager_resource(init_context: InitResourceContext):
    """Dagster resource for database management."""
    db_path = init_context.resource_config.get("database_path", "data/reviews.db")
    return DatabaseManager(db_path)


@op(config_schema=ScrapingConfig, required_resource_keys={"scraping_orchestrator"})
async def scrape_product_reviews(context: OpExecutionContext) -> Dict[str, Any]:
    """
    Scrape reviews for specified products.

    Returns scraping results with metrics for monitoring.
    """
    logger = get_dagster_logger()
    orchestrator = context.resources.scraping_orchestrator
    config = context.op_config

    logger.info(f"Starting scraping operation for {len(config['product_urls'])} products")

    try:
        # Run the scraping operation
        results = await orchestrator.scrape_all_products(config["product_urls"])

        # Log metrics for monitoring
        context.log_event(
            AssetMaterialization(
                asset_key="scraped_reviews",
                metadata={
                    "total_reviews": MetadataValue.int(results["total_scraped"]),
                    "new_reviews": MetadataValue.int(results["total_new_reviews"]),
                    "errors": MetadataValue.int(results["errors"]),
                    "processing_time": MetadataValue.float(results["processing_time"]),
                    "urls_processed": MetadataValue.int(len(config["product_urls"])),
                },
            )
        )

        # Data quality checks
        if results["errors"] > len(config["product_urls"]) * 0.5:
            context.log_event(
                ExpectationResult(
                    success=False,
                    label="error_rate_check",
                    description=f"Error rate too high: {results['errors']} errors out of {len(config['product_urls'])} URLs",
                )
            )
        else:
            context.log_event(
                ExpectationResult(
                    success=True,
                    label="error_rate_check",
                    description="Error rate within acceptable limits",
                )
            )

        logger.info(
            f"Scraping completed: {results['total_scraped']} reviews, {results['errors']} errors"
        )
        return results

    except Exception as e:
        logger.error(f"Scraping operation failed: {e}")
        raise


@op(required_resource_keys={"database_manager"})
def validate_scraped_data(
    context: OpExecutionContext, scraping_results: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Validate the quality and integrity of scraped data.
    """
    logger = get_dagster_logger()
    db_manager = context.resources.database_manager

    logger.info("Starting data validation")

    try:
        # Get recent reviews for validation
        recent_reviews = db_manager.get_reviews(limit=1000)

        validation_results = {
            "total_records": len(recent_reviews),
            "missing_ratings": 0,
            "missing_text": 0,
            "duplicate_reviews": 0,
            "invalid_ratings": 0,
        }

        seen_review_ids = set()

        for review in recent_reviews:
            # Check for missing or invalid ratings
            if not review.get("rating") or review["rating"] == 0:
                validation_results["missing_ratings"] += 1
            elif not (0 <= review["rating"] <= 5):
                validation_results["invalid_ratings"] += 1

            # Check for missing review text
            if not review.get("review_text") or len(review["review_text"].strip()) == 0:
                validation_results["missing_text"] += 1

            # Check for duplicates
            review_id = review.get("review_id")
            if review_id in seen_review_ids:
                validation_results["duplicate_reviews"] += 1
            else:
                seen_review_ids.add(review_id)

        # Calculate quality metrics
        total_records = validation_results["total_records"]
        if total_records > 0:
            quality_score = 1 - (
                (
                    validation_results["missing_ratings"]
                    + validation_results["missing_text"]
                    + validation_results["duplicate_reviews"]
                    + validation_results["invalid_ratings"]
                )
                / total_records
            )
        else:
            quality_score = 0

        validation_results["quality_score"] = quality_score

        # Log validation metrics
        context.log_event(
            AssetMaterialization(
                asset_key="data_validation",
                metadata={
                    "quality_score": MetadataValue.float(quality_score),
                    "total_records": MetadataValue.int(total_records),
                    "missing_ratings": MetadataValue.int(validation_results["missing_ratings"]),
                    "missing_text": MetadataValue.int(validation_results["missing_text"]),
                    "duplicates": MetadataValue.int(validation_results["duplicate_reviews"]),
                    "invalid_ratings": MetadataValue.int(validation_results["invalid_ratings"]),
                },
            )
        )

        # Quality expectation
        if quality_score >= 0.8:
            context.log_event(
                ExpectationResult(
                    success=True,
                    label="data_quality_check",
                    description=f"Data quality score: {quality_score:.2f}",
                )
            )
        else:
            context.log_event(
                ExpectationResult(
                    success=False,
                    label="data_quality_check",
                    description=f"Data quality below threshold: {quality_score:.2f}",
                )
            )

        logger.info(f"Data validation completed. Quality score: {quality_score:.2f}")
        return validation_results

    except Exception as e:
        logger.error(f"Data validation failed: {e}")
        raise


@op(required_resource_keys={"database_manager"})
def export_reviews_data(context: OpExecutionContext, validation_results: Dict[str, Any]) -> str:
    """
    Export validated review data for analysis.
    """
    logger = get_dagster_logger()
    db_manager = context.resources.database_manager

    try:
        # Generate timestamped export file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        export_file = f"exports/reviews_export_{timestamp}.json"

        # Export data
        export_count = db_manager.export_to_json(export_file)

        context.log_event(
            AssetMaterialization(
                asset_key="exported_data",
                metadata={
                    "export_file": MetadataValue.text(export_file),
                    "exported_records": MetadataValue.int(export_count),
                    "export_timestamp": MetadataValue.text(timestamp),
                },
            )
        )

        logger.info(f"Exported {export_count} reviews to {export_file}")
        return export_file

    except Exception as e:
        logger.error(f"Data export failed: {e}")
        raise


@op(required_resource_keys={"database_manager"})
def cleanup_old_data(context: OpExecutionContext) -> Dict[str, int]:
    """
    Clean up old data to manage storage space.
    """
    logger = get_dagster_logger()
    db_manager = context.resources.database_manager

    try:
        # Clean data older than 90 days
        deleted_count = db_manager.cleanup_old_data(days=90)

        cleanup_results = {
            "deleted_records": deleted_count,
            "cleanup_date": datetime.now().isoformat(),
        }

        context.log_event(
            AssetMaterialization(
                asset_key="data_cleanup",
                metadata={
                    "deleted_records": MetadataValue.int(deleted_count),
                    "retention_days": MetadataValue.int(90),
                },
            )
        )

        logger.info(f"Cleaned up {deleted_count} old records")
        return cleanup_results

    except Exception as e:
        logger.error(f"Data cleanup failed: {e}")
        raise


# Job definitions
@job(
    resource_defs={
        "scraping_orchestrator": scraping_orchestrator_resource,
        "database_manager": database_manager_resource,
    }
)
def review_scraping_pipeline():
    """
    Main review scraping pipeline.

    This job orchestrates the complete review scraping workflow:
    1. Scrape reviews from configured product URLs
    2. Validate data quality
    3. Export data for analysis
    4. Cleanup old data
    """
    scraping_results = scrape_product_reviews()
    validation_results = validate_scraped_data(scraping_results)
    export_file = export_reviews_data(validation_results)
    cleanup_results = cleanup_old_data()


# Schedules
@schedule(
    job=review_scraping_pipeline,
    cron_schedule="0 9 * * *",  # Daily at 9 AM
    default_status=DefaultSensorStatus.RUNNING,
)
def daily_review_scraping_schedule(context):
    """
    Daily schedule for review scraping.
    """
    # Load product URLs from configuration
    with open("config/config.json", "r") as f:
        config = json.load(f)

    return RunRequest(
        run_config={
            "ops": {
                "scrape_product_reviews": {
                    "config": {
                        "product_urls": config.get("target_products", []),
                        "max_retries": 3,
                        "rate_limit_requests": 10,
                        "rate_limit_window": 60,
                    }
                }
            }
        }
    )


@schedule(
    job=review_scraping_pipeline,
    cron_schedule="0 2 * * 0",  # Weekly on Sunday at 2 AM
    default_status=DefaultSensorStatus.RUNNING,
)
def weekly_comprehensive_scraping_schedule(context):
    """
    Weekly comprehensive scraping with extended product list.
    """
    # Extended product list for comprehensive weekly scraping
    extended_urls = [
        # Add more comprehensive product URLs here
        "https://www.walmart.com/ip/dashing-diva-example-1",
        "https://www.walmart.com/ip/dashing-diva-example-2",
        # Would include all Dashing Diva products across retailers
    ]

    return RunRequest(
        run_config={
            "ops": {
                "scrape_product_reviews": {
                    "config": {
                        "product_urls": extended_urls,
                        "max_retries": 5,
                        "rate_limit_requests": 5,  # More conservative for large batch
                        "rate_limit_window": 60,
                    }
                }
            }
        }
    )


# Sensors
@sensor(job=review_scraping_pipeline, default_status=DefaultSensorStatus.RUNNING)
def new_product_sensor(context):
    """
    Sensor to detect new products and trigger scraping.
    """
    # In a real implementation, this would monitor for new product additions
    # For this example, we'll check a products file or API

    try:
        # Check for new products file
        new_products_file = "config/new_products.json"
        if Path(new_products_file).exists():
            with open(new_products_file, "r") as f:
                new_products = json.load(f)

            if new_products.get("urls"):
                # Remove the file after processing
                Path(new_products_file).unlink()

                return RunRequest(
                    run_config={
                        "ops": {
                            "scrape_product_reviews": {
                                "config": {
                                    "product_urls": new_products["urls"],
                                    "max_retries": 3,
                                    "rate_limit_requests": 10,
                                    "rate_limit_window": 60,
                                }
                            }
                        }
                    }
                )

    except Exception as e:
        context.log.error(f"Error in new product sensor: {e}")

    return SkipReason("No new products detected")


# Error monitoring sensor
@sensor(job=review_scraping_pipeline, default_status=DefaultSensorStatus.RUNNING)
def error_monitoring_sensor(context):
    """
    Monitor for high error rates and trigger remediation.
    """
    try:
        # Check recent scraping results for high error rates
        db_manager = DatabaseManager()

        # This would typically query a monitoring database
        # For this example, we'll simulate error detection

        # If high error rate detected, trigger a retry run
        # This is a simplified example
        return SkipReason("No high error rates detected")

    except Exception as e:
        context.log.error(f"Error monitoring sensor failed: {e}")
        return SkipReason("Error monitoring failed")


# Repository definition
from dagster import repository


@repository
def dashing_diva_repository():
    """
    Dagster repository containing all jobs, schedules, and sensors
    for the Dashing Diva review scraping system.
    """
    return [
        review_scraping_pipeline,
        daily_review_scraping_schedule,
        weekly_comprehensive_scraping_schedule,
        new_product_sensor,
        error_monitoring_sensor,
    ]
