-- PostgreSQL initialization script for BaluHost
-- This script is automatically run on first container startup

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";    -- For UUID generation
CREATE EXTENSION IF NOT EXISTS "pg_trgm";      -- For text search with trigrams
CREATE EXTENSION IF NOT EXISTS "btree_gin";    -- For GIN indexes on btree types

-- Create database if it doesn't exist (handled by Docker environment)
-- Create user if needed (handled by Docker environment)

-- Grant necessary privileges
GRANT ALL PRIVILEGES ON DATABASE baluhost TO baluhost;

-- Set timezone to UTC
ALTER DATABASE baluhost SET timezone TO 'UTC';

-- Performance tuning for small to medium deployments
ALTER SYSTEM SET shared_buffers = '256MB';
ALTER SYSTEM SET effective_cache_size = '1GB';
ALTER SYSTEM SET maintenance_work_mem = '64MB';
ALTER SYSTEM SET checkpoint_completion_target = 0.9;
ALTER SYSTEM SET wal_buffers = '16MB';
ALTER SYSTEM SET default_statistics_target = 100;
ALTER SYSTEM SET random_page_cost = 1.1;
ALTER SYSTEM SET effective_io_concurrency = 200;
ALTER SYSTEM SET work_mem = '8MB';
ALTER SYSTEM SET min_wal_size = '1GB';
ALTER SYSTEM SET max_wal_size = '4GB';

-- Note: These settings require a PostgreSQL restart to take effect
-- They will be applied on container restart
