# Makefile for Dashing Diva Review Scraper

.PHONY: help install test lint format clean docker-build docker-run setup deploy

# Default target
help:
	@echo "Dashing Diva Review Scraper - Available Commands:"
	@echo ""
	@echo "Setup and Installation:"
	@echo "  setup          - Run complete setup (install deps, create dirs, init db)"
	@echo "  install        - Install python3 dependencies"
	@echo "  install-dev    - Install development dependencies"
	@echo ""
	@echo "Development:"
	@echo "  test           - Run all tests"
	@echo "  test-unit      - Run unit tests only"
	@echo "  test-integration - Run integration tests only"
	@echo "  test-coverage  - Run tests with coverage report"
	@echo "  lint           - Run linting checks"
	@echo "  format         - Format code with black and isort"
	@echo "  clean          - Clean up temporary files"
	@echo ""
	@echo "Application:"
	@echo "  scrape         - Run scraper with default config"
	@echo "  dashboard      - Start web dashboard"
	@echo "  init-config    - Create sample configuration"
	@echo ""
	@echo "Docker:"
	@echo "  docker-build   - Build Docker image"
	@echo "  docker-run     - Run application in Docker"
	@echo "  docker-dev     - Run development environment with docker-compose"
	@echo ""
	@echo "Deployment:"
	@echo "  deploy-dev     - Deploy to development environment"
	@echo "  deploy-staging - Deploy to staging environment"
	@echo "  deploy-prod    - Deploy to production environment"

# Setup and Installation
setup:
	@echo "🚀 Running complete setup..."
	./scripts/setup.sh

install:
	@echo "📦 Installing dependencies..."
	pip install -r requirements.txt

install-dev: install
	@echo "🔧 Installing development dependencies..."
	pip install -e ".[dev]"

# Development
test:
	@echo "🧪 Running all tests..."
	python3 -m pytest tests/ -v

test-unit:
	@echo "🧪 Running unit tests..."
	python3 -m pytest tests/unit/ -v

test-integration:
	@echo "🧪 Running integration tests..."
	python3 -m pytest tests/integration/ -v

test-coverage:
	@echo "📊 Running tests with coverage..."
	python3 -m pytest tests/ --cov=src --cov-report=html --cov-report=term

lint:
	@echo "🔍 Running linting checks..."
	flake8 src/ tests/
	mypy src/
	black --check src/ tests/
	isort --check-only src/ tests/

format:
	@echo "🎨 Formatting code..."
	black src/ tests/ main.py
	isort src/ tests/ main.py

clean:
	@echo "🧹 Cleaning up..."
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	rm -rf build/
	rm -rf dist/
	rm -rf .coverage
	rm -rf htmlcov/
	rm -rf .pytest_cache/
	rm -rf .mypy_cache/

# Application
scrape:
	@echo "🕷️ Running scraper..."
	python3 main.py scrape

dashboard:
	@echo "📊 Starting dashboard..."
	python3 main.py dashboard

init-config:
	@echo "⚙️ Creating sample configuration..."
	python3 main.py init-config

# Docker
docker-build:
	@echo "🐳 Building Docker image..."
	docker build -f docker/Dockerfile -t dashing-diva-scraper:latest .

docker-run: docker-build
	@echo "🚀 Running application in Docker..."
	docker run -p 5000:5000 -v $(PWD)/data:/app/data dashing-diva-scraper:latest

docker-dev:
	@echo "🔧 Starting development environment..."
	docker-compose -f docker/docker-compose.yml up

# Deployment
deploy-dev:
	@echo "🔧 Deploying to development..."
	./scripts/deploy.sh development

deploy-staging:
	@echo "🎭 Deploying to staging..."
	./scripts/deploy.sh staging

deploy-prod:
	@echo "🏭 Deploying to production..."
	./scripts/deploy.sh production

# Database operations
db-backup:
	@echo "💾 Creating database backup..."
	cp data/reviews.db data/reviews_backup_$(shell date +%Y%m%d_%H%M%S).db

db-migrate:
	@echo "🗄️ Running database migrations..."
	PYTHONPATH=src python3 -c "from dashing_diva_scraper.database.manager import DatabaseManager; DatabaseManager().init_database()"

# Monitoring
stats:
	@echo "📈 Showing database statistics..."
	python3 main.py stats

health-check:
	@echo "🔍 Running health check..."
	curl -f http://localhost:5000/api/health || echo "Service not running"

# Documentation
docs-build:
	@echo "📚 Building documentation..."
	@echo "Documentation would be built here (e.g., with Sphinx)"

docs-serve:
	@echo "📖 Serving documentation..."
	@echo "Documentation server would start here"
