# Supabase Setup Guide for AI History Agent

This guide will walk you through setting up your Supabase PostgreSQL database so it can successfully store and retrieve your YouTube and Google Search history, as well as perform semantic vector searches.

## 1. Create a Supabase Project
1. Go to [Supabase](https://supabase.com/) and create a free account if you don't have one.
2. Click **New Project**, choose your organization, and give your project a name (e.g., `History AI RAG`).
3. **Important:** Enter a strong **Database Password**. Keep this password handy! You will need to enter this raw password in the Flutter frontend app.
4. Choose a region closest to you and click **Create new project**. It will take a few minutes for the database to provision.

## 2. Get Your Connection Details
Once your project is ready, you need to find your Postgres connection string for the Flutter app.

1. Go to your Supabase Project Dashboard.
2. Click the **"Connect"** button in the top navigation bar.
3. In the modal that opens, look for the connection string options  select direct connection.
4.Select transaction pooler
4. scroll down and copy  connection string.
5. Copy the connection string. It will look something like this:
   ```text
   postgresql://postgres.[PROJECT-REF]:[YOUR-PASSWORD]@aws-0-REGION.pooler.supabase.com:6543/postgres
   ```
6. **In the Flutter App:** 
   - Paste this exact string into the **Connection URL** field. 
   - Paste your actual raw password into the **Raw Database Password** field. 

*(Note: The Flutter app will securely extract the `Host`, `Port`, and `Project Ref` directly from your Connection URL!)*

## 3. Set Up the Database Tables & Vector Extension
Our RAG (Retrieval-Augmented Generation) application requires `pgvector` to store AI embeddings and perform semantic search. 

1. On the left sidebar in Supabase, click on **SQL Editor**.
2. Click **New query**.
3. Copy and paste the following SQL script into the editor:

```sql
-- 1. Create the Search History Table
CREATE TABLE search_history (
    id SERIAL PRIMARY KEY,
    service TEXT,
    action TEXT,
    timestamp TIMESTAMP,
    links TEXT,
    actual_website TEXT,
    page_title TEXT,
    drift_attempts INT DEFAULT 0 -- Added to prevent infinite taxonomy drift loops on noise
);

-- 2. Create the YouTube History Table
CREATE TABLE youtube_history (
    id SERIAL PRIMARY KEY,
    service TEXT,
    action TEXT,
    timestamp TIMESTAMP,
    links TEXT,
    video_id TEXT,
    video_title TEXT,
    video_description TEXT,
    channel_title TEXT,
    category_id BIGINT,
    category_name TEXT,
    view_count BIGINT,
    like_count BIGINT,
    drift_attempts INT DEFAULT 0 -- Added to prevent infinite taxonomy drift loops on noise
);

-- 3. Create Performance Indexes
CREATE INDEX idx_search_time ON search_history(timestamp);
CREATE INDEX idx_youtube_time ON youtube_history(timestamp);

-- ==========================================
-- 🔐 SECURITY: ENABLE ROW LEVEL SECURITY
-- ==========================================
ALTER TABLE search_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE youtube_history ENABLE ROW LEVEL SECURITY;

-- By enabling RLS without creating any "ALLOW" policies, 
-- we have effectively created a "Default Deny All" rule.
-- The auto-generated API will now reject all read/write requests.
-- Your Python script will still work because it uses the Postgres superuser credentials.

-- 1. Enable the vector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- 2. Add the 384-dimensional vector column to your YouTube table
ALTER TABLE youtube_history 
ADD COLUMN embedding vector(384);

-- 3. Add the 384-dimensional vector column to your Search table
ALTER TABLE search_history 
ADD COLUMN embedding vector(384);
```

4. Click the **Run** button at the bottom right. You should see a "Success" message indicating that your tables and vector extension are ready.

## 4. You're All Set! 🎉
You can now run your FastAPI backend and Flutter frontend. 
When you click **Upload CSV** in the app, simply provide your YouTube API Key (if processing YouTube data), your newly copied **Connection URL**, and your **Raw Database Password**, and the backend will automatically handle the rest!
