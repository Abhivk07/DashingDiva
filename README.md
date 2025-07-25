# Dashing Diva Review Scraper

## How to Run

### Quick Start (3 commands)

```bash
# 1. Activate environment
source venv/bin/activate

# 2. Collect reviews (takes 30-60 seconds)
make scrape

# 3. View dashboard
make dashboard
```

Then open: **http://localhost:5000**

### What You Get

- **44+ reviews** from Walmart, Target, ULTA
- **Interactive filtering** by retailer, rating, date
- **Visual analytics** and charts
- **Export capabilities** (JSON format)

### Alternative Commands

```bash
# Run scraper directly
python3 main.py scrape

# Start dashboard directly  
python3 main.py dashboard

# Docker (one command)
make docker-build && docker run -p 5000:5000 dashing-diva-scraper:latest
```

### Troubleshooting

**Port already in use:**
```bash
# Kill existing process
pkill -f "python3 main.py dashboard"
# Then restart
make dashboard
```

**No reviews collected:**
```bash
# Check internet connection, try again
make scrape
```

## Files Created

- `data/reviews.db` - SQLite database with reviews
- `exports/scrape_results_*.json` - Exported review data
- `logs/` - Application logs

That's it! The system is pre-configured with Dashing Diva product URLs and ready to run.
