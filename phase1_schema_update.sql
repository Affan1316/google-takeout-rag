-- Phase 1 Schema Update for Hybrid Aggregation Pipeline
-- Run this in your Supabase SQL Editor
SET statement_timeout = '10min'; -- Prevents upstream timeout on massive tables

-- 1. Create the Hierarchical Interest Categories Table
CREATE TABLE interest_categories (
    id SERIAL PRIMARY KEY,
    parent_id INT REFERENCES interest_categories(id) ON DELETE CASCADE,
    category_name TEXT NOT NULL,
    embedding vector(384), -- Dimension for BAAI/bge-small-en-v1.5
    is_global BOOLEAN DEFAULT true,
    user_id UUID, -- For future multi-tenancy (Supabase Auth)
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 2. Create the HNSW Index for ultra-fast vector searches
-- We use vector_cosine_ops because we are measuring cosine distance/similarity (<=>)
-- We drop the index if it exists to apply the optimized ef_construction = 256 parameter.
DROP INDEX IF EXISTS interest_categories_embedding_idx;
CREATE INDEX interest_categories_embedding_idx ON interest_categories USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 256);

-- Add drift_attempts column to existing raw history tables to handle drift cycle limits
ALTER TABLE youtube_history ADD COLUMN IF NOT EXISTS drift_attempts INT DEFAULT 0;
ALTER TABLE search_history ADD COLUMN IF NOT EXISTS drift_attempts INT DEFAULT 0;

-- 3. Create the Intermediate Mapping Table (log_classifications)
-- This decouples classification from the heavy historical tables
CREATE TABLE log_classifications (
    id SERIAL PRIMARY KEY,
    youtube_log_id INT REFERENCES youtube_history(id) ON DELETE CASCADE,
    search_log_id INT REFERENCES search_history(id) ON DELETE CASCADE,
    category_id INT REFERENCES interest_categories(id) ON DELETE CASCADE,
    confidence_score FLOAT,
    embedding_model_version TEXT DEFAULT 'BAAI/bge-small-en-v1.5',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    -- Ensure this classification maps to exactly ONE historical log (either YouTube or Search)
    CHECK (
        (youtube_log_id IS NOT NULL AND search_log_id IS NULL) OR 
        (youtube_log_id IS NULL AND search_log_id IS NOT NULL)
    )
);

-- 4. Add performance indexes for the mapping table
CREATE INDEX idx_log_class_youtube ON log_classifications(youtube_log_id);
CREATE INDEX idx_log_class_search ON log_classifications(search_log_id);
CREATE INDEX idx_log_class_category ON log_classifications(category_id);

-- (Removed ALTER TABLE for embedding_model_version to prevent database locking issues)
-- ==========================================
-- 🔐 SECURITY: ENABLE ROW LEVEL SECURITY
-- ==========================================
ALTER TABLE interest_categories ENABLE ROW LEVEL SECURITY;
ALTER TABLE log_classifications ENABLE ROW LEVEL SECURITY;
