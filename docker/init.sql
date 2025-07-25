-- Initialize the Dashing Diva Reviews database
-- This script runs when the PostgreSQL container starts for the first time

-- Create extensions if needed
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Create indexes for better performance (the tables will be created by the application)
-- These will only be created when the tables exist

-- Note: The actual table creation is handled by the Python application
-- This file is mainly for any database-level setup that needs to happen

-- Example: Create a function for updated_at timestamps
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Grant permissions to the scraper user
GRANT ALL PRIVILEGES ON DATABASE dashing_diva_reviews TO scraper_user;

GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO scraper_user;

GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO scraper_user;

-- Allow the user to create tables
ALTER USER scraper_user CREATEDB;