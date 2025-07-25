"""
Dashing Diva Review Scraper

A production-ready web scraper for collecting customer reviews from major retailers.
Designed for the Dashing Diva DevOps & Data Engineering take-home assessment.
"""

__version__ = "1.0.0"
__author__ = "DevOps & Data Engineering Candidate"
__email__ = "candidate@example.com"

from .database.manager import DatabaseManager
from .models.review import ReviewData
from .orchestration.orchestrator import ReviewScrapingOrchestrator

__all__ = ["ReviewData", "ReviewScrapingOrchestrator", "DatabaseManager"]
