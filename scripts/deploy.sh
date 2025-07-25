#!/bin/bash
# Deployment script for Dashing Diva Review Scraper

set -e

echo "🚀 Deploying Dashing Diva Review Scraper..."

# Environment (default to production)
ENVIRONMENT=${1:-production}
echo "📋 Environment: $ENVIRONMENT"

# Build Docker image
echo "🐳 Building Docker image..."
docker build \
    -f docker/Dockerfile \
    --target production \
    -t dashing-diva-scraper:latest \
    -t dashing-diva-scraper:$ENVIRONMENT \
    .

# Run pre-deployment tests
echo "🧪 Running pre-deployment tests..."
docker run --rm \
    -v $(pwd)/tests:/app/tests \
    -v $(pwd)/config:/app/config \
    dashing-diva-scraper:latest \
    python3 -m pytest tests/ --tb=short

# Deploy based on environment
case $ENVIRONMENT in
    "development")
        echo "🔧 Deploying to development..."
        docker-compose -f docker/docker-compose.yml up -d
        ;;
    "staging")
        echo "🎭 Deploying to staging..."
        # Add staging deployment commands here
        echo "Staging deployment would go here"
        ;;
    "production")
        echo "🏭 Deploying to production..."
        # Production deployment commands
        echo "Production deployment would go here"
        echo "Consider using:"
        echo "- kubectl apply -f k8s/"
        echo "- helm upgrade dashing-diva-scraper ./helm-chart"
        echo "- docker push to registry and update service"
        ;;
    *)
        echo "❌ Unknown environment: $ENVIRONMENT"
        exit 1
        ;;
esac

echo "✅ Deployment completed for $ENVIRONMENT!"

# Health check
echo "🔍 Running health check..."
sleep 10  # Wait for services to start

if command -v curl &> /dev/null; then
    if curl -f http://localhost:5000/api/health; then
        echo "✅ Health check passed!"
    else
        echo "❌ Health check failed!"
        exit 1
    fi
else
    echo "⚠️ curl not available, skipping health check"
fi

echo "🎉 Deployment successful!"
