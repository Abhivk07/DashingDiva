#!/bin/bash
# Setup script for Dashing Diva Review Scraper

set -e  # Exit on any error

echo "🚀 Setting up Dashing Diva Review Scraper..."

# Check python3 version
python3_version=$(python33 --version 2>&1 | awk '{print $2}' | cut -d. -f1,2)
required_version="3.11"

if [ "$(printf '%s\n' "$required_version" "$python3_version" | sort -V | head -n1)" != "$required_version" ]; then
    echo "❌ python3 $required_version or higher is required. Found: $python3_version"
    exit 1
fi

echo "✅ python3 version check passed: $python3_version"

# Create virtual environment
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python33 -m venv venv
fi

# Activate virtual environment
echo "🔄 Activating virtual environment..."
source venv/bin/activate

# Upgrade pip
echo "⬆️ Upgrading pip..."
pip install --upgrade pip

# Install dependencies
echo "📚 Installing dependencies..."
pip install -r requirements.txt

# Create required directories
echo "📁 Creating required directories..."
mkdir -p data logs exports config

# Initialize database
echo "🗄️ Initializing database..."
python3 -c "
from src.dashing_diva_scraper.database.manager import DatabaseManager
db = DatabaseManager('data/reviews.db')
print('Database initialized successfully')
"

# Create sample configuration if it doesn't exist
if [ ! -f "config/config.json" ]; then
    echo "⚙️ Creating sample configuration..."
    python3 main.py init-config
fi

# Run tests to verify installation
echo "🧪 Running tests to verify installation..."
python3 -m pytest tests/ -v --tb=short || echo "⚠️ Some tests failed, but setup can continue"

echo "✅ Setup completed successfully!"
echo ""
echo "🎯 Next steps:"
echo "1. Edit config/config.json with your target product URLs"
echo "2. Run 'python3 main.py scrape' to start scraping"
echo "3. Run 'python3 main.py dashboard' to start the web interface"
echo ""
echo "📖 For more information, see README.md"
