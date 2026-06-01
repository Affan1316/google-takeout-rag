import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
import urllib.parse
import io
import json
import pandas as pd
import os
import re
import time
import requests
import numpy as np
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import create_engine, text
from typing import List, Any, Optional
from datetime import datetime
from langchain_community.utilities.sql_database import SQLDatabase
from langchain_community.agent_toolkits.sql.toolkit import SQLDatabaseToolkit
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from langchain_core.tools import tool
from langchain_huggingface import HuggingFaceEmbeddings
from parse_takeout import parse_takeout_html
from db_config import set_db_credentials, validate_connection

CSV_PROCESSOR_AVAILABLE = True

# ==========================================
# CORE HISTORY PROCESSING ENGINE (Merged from main.py)
# ==========================================

def fetch_dynamic_categories(api_key):
    """Fetches up-to-date YouTube categories directly from the API."""
    print("Fetching active YouTube categories...")
    url = f"https://www.googleapis.com/youtube/v3/videoCategories?part=snippet&regionCode=US&key={api_key}"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            return {item['id']: item['snippet']['title'] for item in data.get('items', [])}
        else:
            print(f"Warning: Could not fetch categories (Status {response.status_code}). Falling back to unknown.")
            return {}
    except Exception as e:
        print(f"Error fetching categories: {e}")
        return {}

class YouTubeQuotaExceededException(Exception):
    """Exception raised when the YouTube API quota is exceeded."""
    pass

def fetch_with_retry(url, params, max_retries=3):
    """Handles API requests with exponential backoff for rate limits and fails fast on quota limits."""
    for attempt in range(max_retries):
        try:
            response = requests.get(url, params=params, timeout=10)
            
            if response.status_code == 200:
                return response
            elif response.status_code == 403:
                # Inspect response to see if it's quota exhaustion
                try:
                    err_json = response.json()
                    errors = err_json.get('error', {}).get('errors', [])
                    reasons = [e.get('reason') for e in errors]
                    if 'quotaExceeded' in reasons:
                        print("❌ YouTube API Quota Exceeded! Exiting ingestion pipeline dynamically...")
                        raise YouTubeQuotaExceededException("YouTube API quota exceeded.")
                except (ValueError, TypeError, AttributeError) as json_err:
                    if isinstance(json_err, YouTubeQuotaExceededException):
                        raise
                
                # Treat other 403s as transient
                wait_time = (2 ** attempt) + 1
                print(f"⚠️ Warning (Status 403). Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
                
            elif response.status_code == 429:  # 429: Too Many Requests
                wait_time = (2 ** attempt) + 1
                print(f"⚠️ Rate limited (Status 429). Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                print(f"❌ Error {response.status_code}: {response.text}")
                return None
        except requests.exceptions.Timeout:
            print(f"❌ Timeout on attempt {attempt + 1}")
            continue
        except Exception as e:
            if isinstance(e, YouTubeQuotaExceededException):
                raise
            print(f"❌ Error on attempt {attempt + 1}: {e}")
            return None

    print("❌ Max retries reached. Skipping chunk.")
    return None

def extract_video_id(links):
    if pd.isna(links):
        return None
    match = re.search(r'watch\?v=([a-zA-Z0-9_-]{11})', str(links))
    return match.group(1) if match else None

def enrich_youtube_data(df, api_key):
    """Enriches YouTube CSV data with metadata from YouTube API."""
    if not api_key:
        raise HTTPException(status_code=400, detail="YouTube API key is required for YouTube data processing")
    
    print(f"Processing YouTube data with {len(df)} rows...")
    
    # Extract Video IDs
    df['video_id'] = df['Links'].apply(extract_video_id)
    unique_video_ids = df['video_id'].dropna().unique().tolist()
    print(f"Found {len(unique_video_ids)} unique videos to process.")
    
    if not unique_video_ids:
        print("⚠️ No valid video IDs found")
        return df
    
    # Get Dynamic Categories
    categories_map = fetch_dynamic_categories(api_key)
    
    # Fetch Metadata in Batches with Retry Logic
    YOUTUBE_API_URL = 'https://www.googleapis.com/youtube/v3/videos'
    metadata_list = []
    chunk_size = 50
    
    print("Fetching metadata from YouTube API in batches...")
    quota_exceeded = False
    try:
        for i in range(0, len(unique_video_ids), chunk_size):
            chunk_ids = unique_video_ids[i:i + chunk_size]
            params = {
                'part': 'snippet,statistics',
                'id': ','.join(chunk_ids),
                'key': api_key
            }
            
            response = fetch_with_retry(YOUTUBE_API_URL, params)
            
            if response:
                items = response.json().get('items', [])
                for item in items:
                    snippet = item.get('snippet', {})
                    stats = item.get('statistics', {})
                    cat_id = str(snippet.get('categoryId', ''))
                    
                    # Apply description truncation
                    raw_desc = snippet.get('description', '').replace('\n', ' ')
                    clean_desc = ' '.join(raw_desc.split())[:200]
                    
                    metadata_list.append({
                        'video_id': item['id'],
                        'Video_Title': snippet.get('title', ''),
                        'Video_Description': clean_desc,
                        'Channel_Title': snippet.get('channelTitle', ''),
                        'Category_ID': cat_id,
                        'Category_Name': categories_map.get(cat_id, 'Unknown'),
                        'View_Count': stats.get('viewCount', 0),
                        'Like_Count': stats.get('likeCount', 0)
                    })
            
            # Polite delay to avoid hitting quota bursts
            time.sleep(0.5)
    except YouTubeQuotaExceededException:
        print("⚠️ YouTube API quota exceeded during background indexing. Gracefully saving processed items.")
        quota_exceeded = True
    
    # Merge and return
    print("Merging metadata with original dataset...")
    metadata_df = pd.DataFrame(metadata_list)
    
    if not metadata_df.empty:
        df_enriched = pd.merge(df, metadata_df, on='video_id', how='left')
        df_enriched['Video_Title'] = df_enriched['Video_Title'].astype(str).str.replace(r'\s+', ' ', regex=True).str.strip()
        return df_enriched, quota_exceeded
    else:
        print("⚠️ No metadata generated. Check API quota and keys.")
        return df, quota_exceeded

def get_actual_website(url):
    """Extracts actual website domain from a URL, handling Google redirects."""
    if pd.isna(url) or not isinstance(url, str):
        return np.nan
    
    try:
        parsed_url = urllib.parse.urlparse(url)
        
        # Handle Google Redirect URLs
        if 'google.' in parsed_url.netloc and parsed_url.path == '/url':
            query_params = urllib.parse.parse_qs(parsed_url.query)
            if 'q' in query_params:
                target_url = query_params['q'][0]
                target_parsed = urllib.parse.urlparse(target_url)
                return target_parsed.netloc
        
        return parsed_url.netloc
    
    except Exception as e:
        return "Parsing Error"

def process_search_data(df):
    """Extracts actual website domains from search data."""
    print(f"Processing Search data with {len(df)} rows...")
    df['Actual_Website'] = df['Links'].apply(get_actual_website)
    return df

def detect_service_type(df):
    """Detects service type based on the 'Service' column in the first row."""
    if df.empty:
        raise HTTPException(status_code=400, detail="CSV file is empty")
    
    service = df.iloc[0]['Service'].strip().lower()
    print(f"Detected service type: {service}")
    
    if 'youtube' in service:
        return 'youtube'
    elif 'search' in service:
        return 'search'
    else:
        raise HTTPException(status_code=400, detail=f"Unknown service type: {service}. Expected 'YouTube' or 'Search'")


class DBState:
    engine = None
    agent_executor = None
    project_ref = None
    password = None
    host = None
    port = None
    llm_api_key = None
    is_indexing = False
    indexing_message = "Ready"

# ==========================================
# 2. INITIALIZE MODELS & VECTOR SEARCH
# ==========================================

# Load the BGE model in the API to embed user questions on the fly
print("Loading BGE embedding model...")
embeddings = HuggingFaceEmbeddings(
    model_name="BAAI/bge-small-en-v1.5",
    encode_kwargs={'normalize_embeddings': True}
)

@tool
def semantic_youtube_search(concept: str) -> str:
    """Use this tool when the user asks to find YouTube videos by meaning, concept, topic, or similarity."""
    if not DBState.engine:
        return "Database not connected. Please upload a CSV with credentials first."
        
    # 1. Turn the user's concept into a 384-dimensional vector
    query_vector = embeddings.embed_query(concept)
    
    # 2. Use pgvector to find the 5 closest matches using Cosine Distance (<=>)
    with DBState.engine.connect() as conn:
        result = conn.execute(
            text("""
                SELECT video_title, channel_title 
                FROM youtube_history 
                WHERE embedding IS NOT NULL
                ORDER BY embedding <=> :vec 
                LIMIT 5;
            """),
            {"vec": str(query_vector)}
        )
        rows = result.fetchall()

    if not rows:
        return "No conceptually similar videos found."

    return "Semantically related videos found: " + " | ".join([f"'{r[0]}' by {r[1]}" for r in rows])

@tool
def generate_longitudinal_report(timezone: str = 'Asia/Karachi') -> str:
    """Use this tool when the user asks for a broad, chronological report of their interests over time, or asks how their habits have evolved over the years."""
    if not DBState.engine:
        return "Database not connected."
        
    try:
        import pandas as pd
        import numpy as np
        
        # 1. Fetch raw interaction metrics
        with DBState.engine.connect() as conn:
            query = text("""
                WITH all_logs AS (
                    SELECT 
                        yh.timestamp AT TIME ZONE :tz AS local_time,
                        lc.category_id
                    FROM log_classifications lc
                    JOIN youtube_history yh ON lc.youtube_log_id = yh.id
                    WHERE lc.youtube_log_id IS NOT NULL
                    UNION ALL
                    SELECT 
                        sh.timestamp AT TIME ZONE :tz AS local_time,
                        lc.category_id
                    FROM log_classifications lc
                    JOIN search_history sh ON lc.search_log_id = sh.id
                    WHERE lc.search_log_id IS NOT NULL
                )
                SELECT 
                    DATE_TRUNC('month', local_time) AS log_month,
                    ic.category_name,
                    COUNT(*) as interaction_count
                FROM all_logs
                JOIN interest_categories ic ON all_logs.category_id = ic.id
                GROUP BY log_month, ic.category_name
            """)
            rows = conn.execute(query, {"tz": timezone}).fetchall()
            
        if not rows:
            return "No historical classifications found to generate a longitudinal report."
            
        # 2. Compile metrics in Pandas
        df = pd.DataFrame(rows, columns=['month', 'category', 'count'])
        df['month'] = pd.to_datetime(df['month'])
        df = df.sort_values(['month', 'count'], ascending=[True, False])
        
        # Total interactions over time
        total_interactions = int(df['count'].sum())
        month_counts = df.groupby('month')['count'].sum()
        active_months = len(month_counts)
        
        # Pivot to create a monthly category matrix
        pivot_df = df.pivot(index='month', columns='category', values='count').fillna(0)
        
        # Compute Month-over-Month (MoM) Deltas
        deltas = pivot_df.diff().fillna(0)
        
        # Identify top anomalies / surges (greatest MoM increases)
        surges = []
        for col in deltas.columns:
            max_surge_val = deltas[col].max()
            if max_surge_val > 10:  # Only report meaningful surges
                max_month = deltas[col].idxmax()
                surges.append({
                    "category": col,
                    "surge_size": int(max_surge_val),
                    "month": max_month.strftime('%Y-%m'),
                    "previous_count": int(pivot_df.loc[max_month, col] - max_surge_val)
                })
        surges = sorted(surges, key=lambda x: x['surge_size'], reverse=True)[:5]
        
        # Identify interest decay (greatest drops)
        declines = []
        for col in deltas.columns:
            max_decline_val = deltas[col].min()
            if max_decline_val < -10:
                min_month = deltas[col].idxmin()
                declines.append({
                    "category": col,
                    "decline_size": int(abs(max_decline_val)),
                    "month": min_month.strftime('%Y-%m')
                })
        declines = sorted(declines, key=lambda x: x['decline_size'], reverse=True)[:5]
        
        # Year-by-Year Peak Summaries
        df['year'] = df['month'].dt.year
        yearly_df = df.groupby(['year', 'category'])['count'].sum().reset_index()
        yearly_df = yearly_df.sort_values(['year', 'count'], ascending=[True, False])
        
        yearly_peaks = {}
        for yr in yearly_df['year'].unique():
            yr_subset = yearly_df[yearly_df['year'] == yr]
            top_cat = yr_subset.iloc[0]['category']
            top_count = int(yr_subset.iloc[0]['count'])
            
            # Fetch representative titles for the peak category of that year
            # (Limit to 2 to keep context ultra-tight)
            with DBState.engine.connect() as conn:
                highlight_query = text("""
                    WITH all_logs AS (
                        SELECT 
                            yh.video_title AS log_text,
                            yh.timestamp AT TIME ZONE :tz AS local_time,
                            lc.category_id
                        FROM log_classifications lc
                        JOIN youtube_history yh ON lc.youtube_log_id = yh.id
                        WHERE lc.youtube_log_id IS NOT NULL
                        UNION ALL
                        SELECT 
                            sh.page_title AS log_text,
                            sh.timestamp AT TIME ZONE :tz AS local_time,
                            lc.category_id
                        FROM log_classifications lc
                        JOIN search_history sh ON lc.search_log_id = sh.id
                        WHERE lc.search_log_id IS NOT NULL
                    )
                    SELECT al.log_text
                    FROM all_logs al
                    JOIN interest_categories ic ON al.category_id = ic.id
                    WHERE ic.category_name = :cat_name 
                      AND EXTRACT(YEAR FROM al.local_time) = :year
                      AND al.log_text IS NOT NULL AND al.log_text != ''
                    LIMIT 2
                """)
                h_rows = conn.execute(highlight_query, {"tz": timezone, "cat_name": top_cat, "year": int(yr)}).fetchall()
                
            yearly_peaks[str(yr)] = {
                "top_category": top_cat,
                "yearly_cat_interactions": top_count,
                "representative_topics": [r[0] for r in h_rows if r[0]]
            }
            
        summary = {
            "total_system_interactions": total_interactions,
            "span_of_active_months": active_months,
            "yearly_interest_hubs": yearly_peaks,
            "greatest_interest_surges_mom": surges,
            "greatest_interest_declines_mom": declines
        }
        
        return "Here is the compiled Pandas longitudinal analysis. Synthesize this delta and surge analysis into a highly detailed psychological/interest evolution report:\n" + json.dumps(summary, indent=2)
    except Exception as e:
        return f"Error generating longitudinal report: {str(e)}"

@tool
def get_top_visited_domains(limit: int = 10, start_date: str = None, end_date: str = None) -> str:
    """Use this tool to find the user's most visited website domains. You can optionally filter by a date range (start_date and end_date in 'YYYY-MM-DD' format)."""
    if not DBState.engine:
        return "Database not connected."
    try:
        filters = []
        params = {"limit": limit}
        if start_date:
            filters.append("timestamp >= :start_date")
            params["start_date"] = start_date
        if end_date:
            filters.append("timestamp <= :end_date")
            params["end_date"] = end_date
            
        filter_sql = " AND ".join(filters)
        if filter_sql:
            filter_sql = "WHERE " + filter_sql
            
        query = text(f"""
            SELECT actual_website, COUNT(*) as visit_count 
            FROM search_history 
            {filter_sql}
            GROUP BY actual_website 
            ORDER BY visit_count DESC 
            LIMIT :limit
        """)
        
        with DBState.engine.connect() as conn:
            rows = conn.execute(query, params).fetchall()
            
        if not rows:
            return "No visited domains found within specified filters."
        return "Top visited domains:\n" + "\n".join([f"• {r[0]}: {r[1]} visits" for r in rows if r[0]])
    except Exception as e:
        return f"Error fetching top domains: {str(e)}"

@tool
def get_daily_activity_counts(start_date: str = None, end_date: str = None) -> str:
    """Use this tool to get daily interaction volumes for YouTube watch logs and Google searches. Filters by start_date and end_date ('YYYY-MM-DD')."""
    if not DBState.engine:
        return "Database not connected."
    try:
        filters = []
        params = {}
        if start_date:
            filters.append("timestamp >= :start_date")
            params["start_date"] = start_date
        if end_date:
            filters.append("timestamp <= :end_date")
            params["end_date"] = end_date
            
        filter_sql = " AND ".join(filters)
        if filter_sql:
            filter_sql = "WHERE " + filter_sql
            
        query = text(f"""
            WITH daily_logs AS (
                SELECT DATE(timestamp) as log_day, 'Search' as service FROM search_history {filter_sql}
                UNION ALL
                SELECT DATE(timestamp) as log_day, 'YouTube' as service FROM youtube_history {filter_sql}
            )
            SELECT log_day, service, COUNT(*) as count 
            FROM daily_logs 
            GROUP BY log_day, service 
            ORDER BY log_day ASC, service ASC
        """)
        
        with DBState.engine.connect() as conn:
            rows = conn.execute(query, params).fetchall()
            
        if not rows:
            return "No activity logs found for the specified filters."
        return "Daily activity stats:\n" + "\n".join([f"• {r[0]} ({r[1]}): {r[2]} interactions" for r in rows])
    except Exception as e:
        return f"Error fetching activity counts: {str(e)}"

@tool
def search_history_by_keyword(keyword: str, limit: int = 15) -> str:
    """Use this tool to search for specific web pages, videos, or search queries using keyword matching on page titles, video titles, or URLs."""
    if not DBState.engine:
        return "Database not connected."
    try:
        query = text("""
            WITH matches AS (
                SELECT timestamp, page_title as title, actual_website as source, 'Search' as service, links FROM search_history WHERE page_title ILIKE :kw OR actual_website ILIKE :kw
                UNION ALL
                SELECT timestamp, video_title as title, channel_title as source, 'YouTube' as service, links FROM youtube_history WHERE video_title ILIKE :kw OR channel_title ILIKE :kw
            )
            SELECT timestamp, service, title, source, links 
            FROM matches 
            ORDER BY timestamp DESC 
            LIMIT :limit
        """)
        
        with DBState.engine.connect() as conn:
            rows = conn.execute(query, {"kw": f"%{keyword}%", "limit": limit}).fetchall()
            
        if not rows:
            return f"No logs found matching keyword: '{keyword}'."
        return f"Found matching history records (up to {limit}):\n" + "\n".join([
            f"• [{r[0]}] {r[1]} - '{r[2]}' on {r[3]} ({r[4]})" for r in rows
        ])
    except Exception as e:
        return f"Error searching history: {str(e)}"

# ==========================================
# 3. BUILD THE RAG AGENT (DYNAMIC INITIALIZATION)
# ==========================================
system_instruction = """
You are a highly skilled Data Analyst AI. Your job is to answer questions about the user's YouTube and Google Search history.
You have access to both exact SQL tools, a semantic_youtube_search tool, and highly optimized search tools.

Rules:
1. ALWAYS look at the tables and schema first before writing a query.
2. NEVER execute DML commands (INSERT, UPDATE, DELETE, DROP). Only run SELECT queries.
3. If a query fails, read the error, fix the SQL, and try again.
4. CRITICAL: If a query returns a massive list (like hundreds of dates or items), DO NOT try to list them all. Summarize the total count, list the first 3 and the last 3, and stop.
5. IF the user asks for exact counts, dates, or specific names, use the standard SQL tools.
6. IF the user asks for topics, concepts, meaning, or "videos about X", use the semantic_youtube_search tool.
7. You can combine these tools to give the best answer.
8. When you get the final data, explain the result in a friendly, conversational way.
9. IF the user asks for a broad, multi-year chronological report or how their interests evolved over time, ALWAYS use the generate_longitudinal_report tool.
10. The search_history table has a page_title column containing the browser page title for each visit. Use this column to identify website content, page names, and search/chat topics across any domain or platform. For example, conversation or page topics often appear in the format 'Topic/Page Name - Website Name' (e.g., 'Classics to Modern - Grok', 'Extract Job Description - Claude', 'Sign in - Google Accounts', 'SQL Transaction Guide - StackOverflow', etc.) in the page_title column. When identifying visits to any specific site, check BOTH the actual_website column AND the page_title column.
11. You have highly optimized structured tools: `get_top_visited_domains`, `get_daily_activity_counts`, `search_history_by_keyword`, and `generate_longitudinal_report`. ALWAYS prefer using these high-level tools first before writing or running any custom SQL queries. Only use direct SQL queries when the user's request cannot be answered by the structured tools.
12. If the user asks for date ranges, span of time, or "when did I start/stop learning X" or "from which month to which month did I do Y", DO NOT query raw records and try to calculate the dates yourself. Instead, write a highly optimized PostgreSQL aggregation query using MIN(timestamp) and MAX(timestamp) on search_history or youtube_history with appropriate LIKE/ILIKE filters to find the exact boundary dates directly in the database in a single row!
"""

TAXONOMY = {
    "Software Engineering": [
        "Machine Learning & AI",
        "Frontend & UI Development",
        "Backend Architecture",
        "Mobile App Development",
        "DevOps & Deployment",
        "Python Programming",
        "Database Optimization"
    ],
    "Productivity & Optimization": [
        "Time Management",
        "Note Taking & Zettelkasten",
        "Focus & Deep Work",
        "Workflow Automation"
    ],
    "Science & Technology": [
        "Cyberpsychology",
        "Hardware & Gadgets",
        "Space & Physics",
        "Cybersecurity"
    ],
    "Entertainment & Leisure": [
        "Video Games & Let's Plays",
        "Movie & TV Reviews",
        "Comedy & Satire",
        "Music & Concerts"
    ],
    "Finance & Business": [
        "Stock Trading & Investing",
        "Entrepreneurship",
        "Cryptocurrency",
        "Personal Finance"
    ],
    "Health & Lifestyle": [
        "Fitness & Workouts",
        "Nutrition & Cooking",
        "Mental Health & Mindfulness",
        "Travel & Vlogs"
    ]
}

def verify_and_initialize_db(db_engine):
    """
    Checks if required tables exist in Supabase.
    If not, automatically executes migrations and seeds taxonomy categories.
    Also ensures all specific columns (like page_title, embedding, and drift_attempts) exist.
    """
    # 1. Enable vector extension
    try:
        with db_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
    except Exception as e:
        print(f"⚠️ Warning enabling vector extension: {e}")

    # 2. search_history upgrades
    try:
        with db_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            conn.execute(text("ALTER TABLE search_history ADD COLUMN IF NOT EXISTS page_title TEXT;"))
            conn.execute(text("ALTER TABLE search_history ADD COLUMN IF NOT EXISTS embedding vector(384);"))
            conn.execute(text("ALTER TABLE search_history ADD COLUMN IF NOT EXISTS drift_attempts INTEGER DEFAULT 0;"))
    except Exception as e:
        print(f"⚠️ Warning upgrading search_history columns: {e}")

    # 3. youtube_history upgrades
    try:
        with db_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            conn.execute(text("ALTER TABLE youtube_history ADD COLUMN IF NOT EXISTS embedding vector(384);"))
            conn.execute(text("ALTER TABLE youtube_history ADD COLUMN IF NOT EXISTS drift_attempts INTEGER DEFAULT 0;"))
    except Exception as e:
        print(f"⚠️ Warning upgrading youtube_history columns: {e}")

    # 4. chat_sessions and chat_messages tables
    try:
        with db_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS chat_sessions (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    last_active TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
            """))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id SERIAL PRIMARY KEY,
                    session_id TEXT REFERENCES chat_sessions(id) ON DELETE CASCADE,
                    text TEXT NOT NULL,
                    is_user BOOLEAN NOT NULL,
                    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    steps JSONB
                );
            """))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_chat_msg_session ON chat_messages(session_id);"))
            
            # Enable Row Level Security (consistent with interest_categories & log_classifications)
            conn.execute(text("ALTER TABLE chat_sessions ENABLE ROW LEVEL SECURITY;"))
            conn.execute(text("ALTER TABLE chat_messages ENABLE ROW LEVEL SECURITY;"))
            
            print("✅ Chat history tables verified/created with RLS enabled!")
    except Exception as e:
        print(f"⚠️ Warning creating chat history tables: {e}")

    print("🔍 Verifying database tables...")
    tables_exist = False
    try:
        with db_engine.connect() as conn:
            conn.execute(text("SELECT 1 FROM interest_categories LIMIT 1"))
            conn.execute(text("SELECT 1 FROM log_classifications LIMIT 1"))
            tables_exist = True
            print("✅ Database tables verified!")
    except Exception:
        print("⚠️ Required tables missing. Initializing database schema...")
        tables_exist = False

    if not tables_exist:
        # 1. Create Core History Tables if they don't exist
        print("▶️ Creating raw history tables and enabling pgvector...")
        init_sql = """
        CREATE TABLE IF NOT EXISTS search_history (
            id SERIAL PRIMARY KEY,
            service TEXT,
            action TEXT,
            timestamp TIMESTAMP,
            links TEXT,
            actual_website TEXT
        );

        CREATE TABLE IF NOT EXISTS youtube_history (
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
            like_count BIGINT
        );

        CREATE INDEX IF NOT EXISTS idx_search_time ON search_history(timestamp);
        CREATE INDEX IF NOT EXISTS idx_youtube_time ON youtube_history(timestamp);

        CREATE EXTENSION IF NOT EXISTS vector;
        """
        try:
            with db_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
                for stmt in init_sql.split(";"):
                    if stmt.strip():
                        conn.execute(text(stmt))
                
                # Add vector columns if they don't exist
                try:
                    conn.execute(text("ALTER TABLE youtube_history ADD COLUMN embedding vector(384)"))
                except Exception as e:
                    if "already exists" not in str(e).lower():
                        print(f"Warning adding embedding to youtube_history: {e}")
                try:
                    conn.execute(text("ALTER TABLE search_history ADD COLUMN embedding vector(384)"))
                except Exception as e:
                    if "already exists" not in str(e).lower():
                        print(f"Warning adding embedding to search_history: {e}")
                # Add page_title column for Chrome history data
                try:
                    conn.execute(text("ALTER TABLE search_history ADD COLUMN page_title TEXT"))
                except Exception as e:
                    if "already exists" not in str(e).lower():
                        print(f"Warning adding page_title to search_history: {e}")
            print("✅ Raw tables and vector extension prepared.")
        except Exception as e:
            print(f"❌ Failed to prepare raw tables: {e}")

        # 2. Run Phase 1 Schema Migration (interest_categories, log_classifications)
        sql_file_path = 'phase1_schema_update.sql'
        if os.path.exists(sql_file_path):
            print(f"▶️ Loading schema from {sql_file_path}...")
            with open(sql_file_path, 'r', encoding='utf-8') as f:
                sql_script = f.read()
            
            with db_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
                statements = [s.strip() for s in sql_script.split(';') if s.strip()]
                for i, statement in enumerate(statements):
                    if not statement or (statement.startswith('--') and len(statement.split('\n')) == 1):
                        continue
                    try:
                        conn.execute(text(statement))
                    except Exception as stmt_e:
                        error_msg = str(stmt_e).lower()
                        if "already exists" in error_msg or "multiple primary keys" in error_msg:
                            continue
                        else:
                            print(f"⚠️ Statement {i+1} warning: {stmt_e}")
            print("✅ Phase 1 schema migration complete.")
        else:
            print(f"❌ Could not find {sql_file_path} for migration!")

        # 3. Seed taxonomy categories using global embeddings model
        print("▶️ Seeding taxonomy categories into database...")
        try:
            with db_engine.connect() as conn:
                result = conn.execute(text("SELECT COUNT(*) FROM interest_categories")).scalar()
                if result == 0:
                    for parent_cat, sub_cats in TAXONOMY.items():
                        print(f"  └─ Seeding parent: {parent_cat}")
                        parent_vector = embeddings.embed_query(parent_cat)
                        
                        res = conn.execute(
                            text("""
                                INSERT INTO interest_categories (category_name, embedding, is_global, parent_id)
                                VALUES (:name, :vec, true, NULL)
                                RETURNING id
                            """),
                            {"name": parent_cat, "vec": str(parent_vector)}
                        )
                        parent_id = res.scalar()
                        
                        for sub_cat in sub_cats:
                            sub_vector = embeddings.embed_query(sub_cat)
                            conn.execute(
                                text("""
                                    INSERT INTO interest_categories (category_name, embedding, is_global, parent_id)
                                    VALUES (:name, :vec, true, :parent)
                                """),
                                {"name": sub_cat, "vec": str(sub_vector), "parent": parent_id}
                            )
                    conn.commit()
                    print("✅ Taxonomy seeding complete!")
                else:
                    print(f"⚠️ Found {result} existing categories, skipping seed.")
        except Exception as e:
            print(f"❌ Error seeding taxonomy: {e}")

def clean_url_to_semantic_text(url):
    """
    Parses and cleans raw URLs into optimized semantic natural language strings.
    Strips protocols, subdomains (like www), query parameters, and splits path slugs
    by common separators (-, _, /, .) into a clean descriptive sentence.
    """
    if not url or not isinstance(url, str):
        return ""
        
    try:
        import urllib.parse
        parsed = urllib.parse.urlparse(url)
        domain = parsed.netloc.lower()
        if domain.startswith("www."):
            domain = domain[4:]
            
        path = parsed.path
        if not path or path == "/":
            return domain
            
        # Clean path segments
        segments = [seg.strip() for seg in path.split("/") if seg.strip()]
        cleaned_segments = []
        
        for segment in segments:
            # Skip purely numeric segments (like IDs) to reduce noise
            if segment.isdigit():
                continue
                
            # Replace common separators with spaces
            seg_text = re.sub(r'[-_\.\+]', ' ', segment)
            # Remove any trailing extension (e.g. html, php)
            seg_text = re.sub(r'\.(html|htm|php|asp|aspx)$', '', seg_text, flags=re.IGNORECASE)
            seg_text = ' '.join(seg_text.split())
            if seg_text:
                cleaned_segments.append(seg_text)
                
        if not cleaned_segments:
            return domain
            
        return f"{domain} / " + " / ".join(cleaned_segments)
    except Exception:
        return url

def generate_embeddings_task(db_engine):
    """Generates BGE-small embeddings for newly uploaded records lacking them."""
    print("🧠 Starting Embedding Generation Task...")
    
    # YouTube embedding
    print("🔍 Fetching YouTube history without embeddings...")
    with db_engine.connect() as conn:
        df = pd.read_sql(
            "SELECT id, video_title, channel_title FROM youtube_history WHERE embedding IS NULL AND video_title IS NOT NULL", 
            conn
        )
        
        if df.empty:
            print("✅ All YouTube videos are already embedded!")
        else:
            print(f"🧠 Generating vectors for {len(df)} YouTube videos...")
            texts = (df['video_title'] + " (Channel: " + df['channel_title'].fillna("Unknown") + ")").tolist()
            vectors = embeddings.embed_documents(texts)
            
            print("💾 Saving YouTube vectors to Supabase...")
            for i, vec in zip(df['id'], vectors):
                conn.execute(
                    text("UPDATE youtube_history SET embedding = :vec WHERE id = :id"),
                    {"vec": str(vec), "id": i}
                )
            conn.commit()
            print("✅ YouTube embedding complete!")
            
    # Search embedding
    print("🔍 Fetching Search history without embeddings...")
    with db_engine.connect() as conn:
        df = pd.read_sql(
            "SELECT id, action, page_title, links FROM search_history WHERE embedding IS NULL AND (action IS NOT NULL OR page_title IS NOT NULL OR links IS NOT NULL)", 
            conn
        )
        
        if df.empty:
            print("✅ All Search queries are already embedded!")
        else:
            print(f"🧠 Generating vectors for {len(df)} Search queries...")
            # Use page_title for embedding when available (richer semantic content),
            # fall back to cleaned URL semantics, and lastly fallback to action text
            texts = []
            for _, row in df.iterrows():
                page_title = str(row.get('page_title', '')).strip() if pd.notna(row.get('page_title')) else ""
                action = str(row.get('action', '')).strip() if pd.notna(row.get('action')) else ""
                links = str(row.get('links', '')).strip() if pd.notna(row.get('links')) else ""
                
                if page_title:
                    texts.append(page_title)
                elif action and not action.startswith("CLICK") and not action.startswith("SEARCH"):
                    texts.append(action.replace("Searched for ", ""))
                elif links:
                    texts.append(clean_url_to_semantic_text(links))
                else:
                    texts.append(action or "Web Visit")
                    
            vectors = embeddings.embed_documents(texts)
            
            print("💾 Saving Search vectors to Supabase...")
            for i, vec in zip(df['id'], vectors):
                conn.execute(
                    text("UPDATE search_history SET embedding = :vec WHERE id = :id"),
                    {"vec": str(vec), "id": i}
                )
            conn.commit()
            print("✅ Search embedding complete!")

def classify_historical_logs_task(db_engine):
    """Classifies unclassified records using nearest interest_categories embedding using optimized local NumPy matrix dot products."""
    print("🧠 Starting High-Performance In-Memory Log Classification...")
    try:
        import numpy as np
        
        # 1. Fetch interest categories
        with db_engine.connect() as conn:
            categories = conn.execute(
                text("SELECT id, category_name, embedding FROM interest_categories WHERE embedding IS NOT NULL")
            ).fetchall()
            
        if not categories:
            print("⚠️ No taxonomy categories with embeddings found. Seeding taxonomy categories first is recommended.")
            return
            
        # Parse category vectors
        cat_ids = []
        cat_vectors = []
        for r in categories:
            emb_val = r[2]
            if emb_val:
                if isinstance(emb_val, str):
                    emb_val = emb_val.strip('[]')
                    vector = [float(x) for x in emb_val.split(',') if x.strip()]
                else:
                    vector = list(emb_val)
                cat_ids.append(r[0])
                cat_vectors.append(vector)
                
        CatMatrix = np.array(cat_vectors)  # Shape: (K, 384)
        
        # 2. Fetch unclassified YouTube logs
        with db_engine.connect() as conn:
            yt_unclassified = conn.execute(text("""
                SELECT id, embedding 
                FROM youtube_history 
                WHERE embedding IS NOT NULL 
                  AND id NOT IN (SELECT youtube_log_id FROM log_classifications WHERE youtube_log_id IS NOT NULL)
            """)).fetchall()
            
        # 3. Process YouTube logs
        batch_size = 5000
        if yt_unclassified:
            print(f"  🧠 Found {len(yt_unclassified)} unclassified YouTube logs. Running NumPy matching...")
            for idx in range(0, len(yt_unclassified), batch_size):
                chunk = yt_unclassified[idx:idx + batch_size]
                
                log_ids = []
                log_vectors = []
                for r in chunk:
                    emb_val = r[1]
                    if isinstance(emb_val, str):
                        emb_val = emb_val.strip('[]')
                        vector = [float(x) for x in emb_val.split(',') if x.strip()]
                    else:
                        vector = list(emb_val)
                    log_ids.append(r[0])
                    log_vectors.append(vector)
                
                LogMatrix = np.array(log_vectors)
                SimMatrix = np.dot(LogMatrix, CatMatrix.T)
                
                best_indices = np.argmax(SimMatrix, axis=1)
                best_scores = np.max(SimMatrix, axis=1)
                
                insert_values = []
                for i, log_id in enumerate(log_ids):
                    best_cat_id = cat_ids[best_indices[i]]
                    score = float(best_scores[i])
                    insert_values.append({
                        "yt_id": log_id,
                        "cat_id": best_cat_id,
                        "score": score
                    })
                
                with db_engine.connect() as insert_conn:
                    with insert_conn.begin():
                        insert_conn.execute(
                            text("""
                                INSERT INTO log_classifications (youtube_log_id, category_id, confidence_score)
                                VALUES (:yt_id, :cat_id, :score)
                            """),
                            insert_values
                        )
                print(f"    Classified and inserted {len(chunk)} YouTube records.")
        else:
            print("  ✅ All YouTube logs are already classified.")
            
        # 4. Fetch unclassified Search logs
        with db_engine.connect() as conn:
            search_unclassified = conn.execute(text("""
                SELECT id, embedding 
                FROM search_history 
                WHERE embedding IS NOT NULL 
                  AND id NOT IN (SELECT search_log_id FROM log_classifications WHERE search_log_id IS NOT NULL)
            """)).fetchall()
            
        # 5. Process Search logs
        if search_unclassified:
            print(f"  🧠 Found {len(search_unclassified)} unclassified Search logs. Running NumPy matching...")
            for idx in range(0, len(search_unclassified), batch_size):
                chunk = search_unclassified[idx:idx + batch_size]
                
                log_ids = []
                log_vectors = []
                for r in chunk:
                    emb_val = r[1]
                    if isinstance(emb_val, str):
                        emb_val = emb_val.strip('[]')
                        vector = [float(x) for x in emb_val.split(',') if x.strip()]
                    else:
                        vector = list(emb_val)
                    log_ids.append(r[0])
                    log_vectors.append(vector)
                
                LogMatrix = np.array(log_vectors)
                SimMatrix = np.dot(LogMatrix, CatMatrix.T)
                
                best_indices = np.argmax(SimMatrix, axis=1)
                best_scores = np.max(SimMatrix, axis=1)
                
                insert_values = []
                for i, log_id in enumerate(log_ids):
                    best_cat_id = cat_ids[best_indices[i]]
                    score = float(best_scores[i])
                    insert_values.append({
                        "sh_id": log_id,
                        "cat_id": best_cat_id,
                        "score": score
                    })
                
                with db_engine.connect() as insert_conn:
                    with insert_conn.begin():
                        insert_conn.execute(
                            text("""
                                INSERT INTO log_classifications (search_log_id, category_id, confidence_score)
                                VALUES (:sh_id, :cat_id, :score)
                            """),
                            insert_values
                        )
                print(f"    Classified and inserted {len(chunk)} Search records.")
        else:
            print("  ✅ All Search logs are already classified.")
            
        print("🎉 In-Memory NumPy Log Classification completed successfully!")
    except Exception as e:
        print(f"❌ Classification failed: {e}")

def run_async_indexing_pipeline(db_engine):
    """Background task runner for embeddings and classifications with transient error recovery"""
    if DBState.is_indexing:
        print("⚠️ Indexing pipeline is already running. Skipping trigger.")
        return
        
    DBState.is_indexing = True
    max_retries = 3
    
    for attempt in range(max_retries):
        try:
            DBState.indexing_message = "Generating BGE-small vector embeddings..."
            generate_embeddings_task(db_engine)
            
            DBState.indexing_message = "Performing nearest-category classification..."
            classify_historical_logs_task(db_engine)
            
            DBState.indexing_message = "Ready"
            print("🎉 Background RAG Ingestion Pipeline completed successfully!")
            DBState.is_indexing = False
            return
        except Exception as e:
            print(f"⚠️ Background RAG Ingestion Pipeline attempt {attempt + 1}/{max_retries} failed: {e}")
            if attempt < max_retries - 1:
                sleep_time = 5 * (attempt + 1)
                DBState.indexing_message = f"Retrying indexing in {sleep_time}s..."
                time.sleep(sleep_time)
            else:
                print("❌ Background RAG Ingestion Pipeline fully failed.")
                DBState.indexing_message = f"Failed: {str(e)}"
                
    DBState.is_indexing = False

def init_db_and_agent(project_ref, password, host, port, llm_api_key):
    """Initializes the DB connection and LangGraph agent dynamically"""
    # 1. Robust validation of inputs
    if not project_ref:
        raise ValueError("Database Project Reference (project_ref) cannot be empty.")
    if not password:
        raise ValueError("Database Password cannot be empty.")
    if not host:
        raise ValueError("Database Host cannot be empty.")
    if not port:
        raise ValueError("Database Port cannot be empty.")
    if not llm_api_key:
        raise ValueError("LLM API Key cannot be empty.")

    safe_password = urllib.parse.quote_plus(password)
    DB_URI = f"postgresql://postgres.{project_ref}:{safe_password}@{host}:{port}/postgres"
    
    # 2. Construct SQLAlchemy engine
    DBState.engine = create_engine(
        DB_URI,
        pool_pre_ping=True,
        pool_recycle=300,
        pool_size=10,
        max_overflow=20
    )
    
    # 3. Connection pre-flight validation
    try:
        with DBState.engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as e:
        DBState.engine = None
        raise ValueError(f"Database connection failed. Please check your credentials and network. Details: {e}")
    
    # Run auto-migration & seeding verification
    verify_and_initialize_db(DBState.engine)
    
    db = SQLDatabase(DBState.engine)

    
    # Initialize LLM dynamically with the user's API Key
    llm = ChatOpenAI(
        api_key=llm_api_key,
        base_url="https://api.deepseek.com",
        model="deepseek-chat",
        temperature=0
    )
    
    toolkit = SQLDatabaseToolkit(db=db, llm=llm)
    tools = toolkit.get_tools() + [
        semantic_youtube_search, 
        generate_longitudinal_report,
        get_top_visited_domains,
        get_daily_activity_counts,
        search_history_by_keyword
    ]
    
    DBState.agent_executor = create_react_agent(model=llm, tools=tools, prompt=system_instruction)
    
    DBState.project_ref = project_ref
    DBState.password = password
    DBState.host = host
    DBState.port = port
    DBState.llm_api_key = llm_api_key
    print("✅ Database and Agent successfully initialized!")

# ==========================================
# 4. DATABASE STORAGE FUNCTIONS
# ==========================================

def insert_chunk_recursive(db_engine, insert_query, chunk, error_callback=None):
    """
    Recursively inserts records into database using binary splitting fallback.
    If a batch fails, it splits into two halves and tries each.
    If a single row fails, it calls the error_callback.
    Massively reduces database I/O compared to linear row-by-row fallback.
    """
    if not chunk:
        return 0
        
    try:
        # Try inserting the entire chunk in a single transaction
        with db_engine.connect() as conn:
            with conn.begin():
                conn.execute(insert_query, chunk)
        return len(chunk)
    except Exception as e:
        # If the chunk is size 1, it's the exact poisoned record!
        if len(chunk) == 1:
            if error_callback:
                error_callback(chunk[0], e)
            return 0
            
        # Binary split the chunk and retry
        mid = len(chunk) // 2
        left_chunk = chunk[:mid]
        right_chunk = chunk[mid:]
        
        print(f"⚠️ Insertion failed for chunk of size {len(chunk)}. Splitting into sub-chunks of size {len(left_chunk)} and {len(right_chunk)}...")
        
        left_inserted = insert_chunk_recursive(db_engine, insert_query, left_chunk, error_callback)
        right_inserted = insert_chunk_recursive(db_engine, insert_query, right_chunk, error_callback)
        return left_inserted + right_inserted

def store_youtube_history(df):
    """Insert enriched YouTube data into database in high-performance batches"""
    import pandas as pd
    import time
    from sqlalchemy.exc import OperationalError
    
    def safe_int(val):
        try:
            return int(float(val)) if pd.notna(val) else 0
        except (ValueError, TypeError):
            return 0

    df = df.where(pd.notnull(df), None)
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            rows_inserted = 0
            # Fetch existing links in a dedicated, short-lived connection
            with DBState.engine.connect() as conn:
                existing_links = {row[0] for row in conn.execute(text("SELECT links FROM youtube_history")).fetchall()}
                
            # Prepare all rows to insert
            insert_data = []
            for _, row in df.iterrows():
                link = row.get('Links')
                if link in existing_links:
                    continue  # Skip duplicate
                
                # Check for duplicates within the current upload itself
                existing_links.add(link)
                
                insert_data.append({
                    "links": link,
                    "title": row.get('Video_Title'),
                    "channel": row.get('Channel_Title'),
                    "views": safe_int(row.get('View_Count')),
                    "likes": safe_int(row.get('Like_Count')),
                    "category": row.get('Category_Name'),
                    "timestamp": row.get('Timestamp')
                })

            if not insert_data:
                print("✅ No new YouTube records to insert")
                return 0

            print(f"Inserting {len(insert_data)} new YouTube records into database in batches...")
            
            # Batch insertion logic with fallback
            batch_size = 500
            insert_query = text("""
                INSERT INTO youtube_history 
                (links, video_title, channel_title, view_count, like_count, 
                 category_name, timestamp, service)
                VALUES (:links, :title, :channel, :views, :likes, :category, 
                        :timestamp, 'YouTube')
            """)
            
            def log_youtube_error(item, err):
                print(f"❌ Failed to insert YouTube row {item.get('links')}: {err}")

            for k in range(0, len(insert_data), batch_size):
                chunk = insert_data[k:k + batch_size]
                rows_inserted += insert_chunk_recursive(DBState.engine, insert_query, chunk, log_youtube_error)
            
            print(f"✅ Successfully stored {rows_inserted} YouTube records in database")
            return rows_inserted
            
        except OperationalError as oe:
            print(f"⚠️ YouTube storage connection error (attempt {attempt + 1}/{max_retries}): {oe}")
            if attempt < max_retries - 1:
                sleep_time = 2 ** attempt
                print(f"   Retrying in {sleep_time} seconds...")
                time.sleep(sleep_time)
            else:
                print("❌ Max retries reached for YouTube history ingestion.")
                raise oe
        except Exception as e:
            print(f"❌ Error storing YouTube history: {e}")
            return 0

def store_search_history(df):
    """Insert processed search data into database in high-performance batches"""
    import pandas as pd
    import time
    from sqlalchemy.exc import OperationalError
    
    df = df.where(pd.notnull(df), None)
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            rows_inserted = 0
            # Fetch existing links in a dedicated, short-lived connection
            with DBState.engine.connect() as conn:
                existing_links = {row[0] for row in conn.execute(text("SELECT links FROM search_history")).fetchall()}
                
            # Prepare all rows to insert
            insert_data = []
            for _, row in df.iterrows():
                link = row.get('Links')
                if link in existing_links:
                    continue  # Skip duplicate
                
                # Check for duplicates within the current upload itself
                existing_links.add(link)
                
                insert_data.append({
                    "links": link,
                    "website": row.get('Actual_Website'),
                    "timestamp": row.get('Timestamp'),
                    "page_title": row.get('Page_Title')
                })

            if not insert_data:
                print("✅ No new Search records to insert")
                return 0

            print(f"Inserting {len(insert_data)} new Search records into database in batches...")
            
            # Batch insertion logic with fallback
            batch_size = 500
            insert_query = text("""
                INSERT INTO search_history 
                (links, actual_website, timestamp, service, page_title)
                VALUES (:links, :website, :timestamp, 'Search', :page_title)
            """)
            
            def log_search_error(item, err):
                print(f"❌ Failed to insert Search row {item.get('links')}: {err}")

            for k in range(0, len(insert_data), batch_size):
                chunk = insert_data[k:k + batch_size]
                rows_inserted += insert_chunk_recursive(DBState.engine, insert_query, chunk, log_search_error)
            
            print(f"✅ Successfully stored {rows_inserted} Search records in database")
            return rows_inserted
            
        except OperationalError as oe:
            print(f"⚠️ Search storage connection error (attempt {attempt + 1}/{max_retries}): {oe}")
            if attempt < max_retries - 1:
                sleep_time = 2 ** attempt
                print(f"   Retrying in {sleep_time} seconds...")
                time.sleep(sleep_time)
            else:
                print("❌ Max retries reached for Search history ingestion.")
                raise oe
        except Exception as e:
            print(f"❌ Error storing search history: {e}")
            return 0

# ==========================================
# 5. BUILD FASTAPI APP
# ==========================================
app = FastAPI(title="Hybrid RAG Agent API with CSV Processing")

from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Define the JSON structure Flutter will send to us
class ChatRequest(BaseModel):
    query: str

class DBMessageSchema(BaseModel):
    text: str
    isUser: bool
    timestamp: str
    steps: Optional[List[Any]] = None

class DBSessionSchema(BaseModel):
    id: str
    title: str
    lastActive: str
    messages: List[DBMessageSchema]

class DBConnectRequest(BaseModel):
    db_project_ref: str
    db_password: str
    db_host: str = "aws-1-ap-northeast-1.pooler.supabase.com"
    db_port: str = "6543"
    llm_api_key: str

# ==========================================
# ENDPOINT 1: CONNECT TO DATABASE (NEW)
# ==========================================
@app.post("/connect-db")
async def connect_db(request: DBConnectRequest):
    """
    Connect to Supabase and initialize the LangGraph Agent.
    """
    try:
        print(f"📥 Received connect-db request: project_ref='{request.db_project_ref}', host='{request.db_host}', port='{request.db_port}'")
        init_db_and_agent(request.db_project_ref, request.db_password, request.db_host, request.db_port, request.llm_api_key)
        return {"status": "success", "message": "Connected to database and initialized agent."}
    except Exception as e:
        print(f"❌ Failed to connect: {e}")
        raise HTTPException(status_code=400, detail=f"Failed to connect: {str(e)}")

# ==========================================
# ENDPOINT 2: CHAT (EXISTING)
# ==========================================
@app.post("/chat")
async def chat_with_agent(request: ChatRequest):
    """
    Main chat endpoint for RAG queries.
    User asks questions about their YouTube/Search history.
    """
    if not DBState.agent_executor:
        raise HTTPException(status_code=400, detail="Database not connected. Please upload a CSV with credentials first to initialize the agent.")

    try:
        # Pass the Flutter user's query into the LangGraph Agent
        result = DBState.agent_executor.invoke({"messages": [("user", request.query)]})
        
        # Extract the final AI text response
        final_answer = result["messages"][-1].content
        
        # Extract agent execution trace steps
        steps = []
        messages = result.get("messages", [])
        i = 0
        while i < len(messages):
            msg = messages[i]
            if msg.type == "ai" and getattr(msg, "tool_calls", None):
                thought = msg.content or ""
                actions = []
                for tc in msg.tool_calls:
                    actions.append({
                        "name": tc.get("name"),
                        "args": tc.get("args")
                    })
                
                observations = []
                i += 1
                while i < len(messages) and messages[i].type == "tool":
                    observations.append(messages[i].content)
                    i += 1
                
                steps.append({
                    "thought": thought,
                    "actions": actions,
                    "observations": observations
                })
                continue
            i += 1
            
        # Return response and execution trace steps to Flutter
        return {
            "response": final_answer,
            "steps": steps
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ==========================================
# ENDPOINT: GET & SYNC CHAT SESSIONS (NEW)
# ==========================================
@app.get("/chat-sessions")
async def get_chat_sessions():
    """
    Get all chat sessions and their messages stored in Supabase,
    ordered by last_active descending.
    """
    if not DBState.engine:
        raise HTTPException(status_code=400, detail="Database not connected.")
    try:
        sessions = []
        with DBState.engine.connect() as conn:
            # Fetch all sessions
            db_sessions = conn.execute(text(
                "SELECT id, title, last_active FROM chat_sessions ORDER BY last_active DESC"
            )).fetchall()
            
            for s in db_sessions:
                s_id, title, last_active = s
                # Fetch messages for this session
                db_messages = conn.execute(text(
                    "SELECT text, is_user, timestamp, steps FROM chat_messages WHERE session_id = :sid ORDER BY id ASC"
                ), {"sid": s_id}).fetchall()
                
                messages = []
                for m in db_messages:
                    m_text, is_user, timestamp, steps = m
                    messages.append({
                        "text": m_text,
                        "isUser": is_user,
                        "timestamp": timestamp.isoformat() if timestamp else datetime.utcnow().isoformat(),
                        "steps": steps
                    })
                
                sessions.append({
                    "id": s_id,
                    "title": title,
                    "lastActive": last_active.isoformat() if last_active else datetime.utcnow().isoformat(),
                    "messages": messages
                })
        return sessions
    except Exception as e:
        print(f"❌ Error fetching chat sessions: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/chat-sessions")
async def save_chat_session(session: DBSessionSchema):
    """
    Save or update a single chat session and its associated messages in Supabase.
    """
    if not DBState.engine:
        raise HTTPException(status_code=400, detail="Database not connected.")
    try:
        # Parse last_active timestamp
        try:
            last_active_dt = datetime.fromisoformat(session.lastActive.replace('Z', '+00:00'))
        except Exception:
            last_active_dt = datetime.utcnow()
            
        with DBState.engine.connect() as conn:
            with conn.begin():
                # Upsert session
                conn.execute(text("""
                    INSERT INTO chat_sessions (id, title, last_active)
                    VALUES (:id, :title, :last_active)
                    ON CONFLICT (id) DO UPDATE 
                    SET title = EXCLUDED.title, last_active = EXCLUDED.last_active
                """), {
                    "id": session.id,
                    "title": session.title,
                    "last_active": last_active_dt
                })
                
                # Delete existing messages to rewrite them
                conn.execute(text(
                    "DELETE FROM chat_messages WHERE session_id = :sid"
                ), {"sid": session.id})
                
                # Insert new messages
                if session.messages:
                    import json
                    insert_data = []
                    for m in session.messages:
                        try:
                            m_timestamp_dt = datetime.fromisoformat(m.timestamp.replace('Z', '+00:00'))
                        except Exception:
                            m_timestamp_dt = datetime.utcnow()
                            
                        insert_data.append({
                            "sid": session.id,
                            "text": m.text,
                            "is_user": m.isUser,
                            "timestamp": m_timestamp_dt,
                            "steps": json.dumps(m.steps) if m.steps is not None else None
                        })
                    
                    conn.execute(text("""
                        INSERT INTO chat_messages (session_id, text, is_user, timestamp, steps)
                        VALUES (:sid, :text, :is_user, :timestamp, CAST(:steps AS jsonb))
                    """), insert_data)
                    
        return {"status": "success", "message": f"Session '{session.id}' saved successfully."}
    except Exception as e:
        print(f"❌ Error saving chat session: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/chat-sessions/{session_id}")
async def delete_chat_session(session_id: str):
    """
    Delete a chat session (and cascade delete its messages) from Supabase.
    """
    if not DBState.engine:
        raise HTTPException(status_code=400, detail="Database not connected.")
    try:
        with DBState.engine.connect() as conn:
            with conn.begin():
                conn.execute(text(
                    "DELETE FROM chat_sessions WHERE id = :sid"
                ), {"sid": session_id})
        return {"status": "success", "message": f"Session '{session_id}' deleted successfully."}
    except Exception as e:
        print(f"❌ Error deleting chat session: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ==========================================
# ENDPOINT 3: CSV UPLOAD & PROCESSING
# ==========================================
@app.post("/upload-and-process-csv")
async def upload_and_process_csv(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    api_key: str = Form(default="")
):
    """
    NEW ENDPOINT: Upload and process CSV files (YouTube or Search data)
    
    - Accepts CSV file from Flutter
    - Detects service type (YouTube or Search)
    - Enriches data using CSV processor
    - Stores results in Supabase database
    - Data becomes immediately available to RAG agent
    
    Parameters:
    - file: CSV file with columns [Service, Action, Timestamp, Links]
    - api_key: YouTube API key (required for YouTube data, optional for Search)
    
    Returns:
    - status: "success" or "error"
    - service_type: "youtube" or "search"
    - rows_processed: Number of rows processed
    - rows_stored: Number of rows successfully stored
    - message: Descriptive message
    """
    
    if not CSV_PROCESSOR_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="CSV processor not available. Please check dependencies."
        )
    
    if not DBState.engine:
        raise HTTPException(status_code=400, detail="Database not connected. Please connect to Supabase first.")

    try:
        # Validate file format
        filename_lower = file.filename.lower()
        if not (filename_lower.endswith('.csv') or filename_lower.endswith('.html') or filename_lower.endswith('.htm')):
            raise HTTPException(status_code=400, detail="Only CSV or Google Takeout HTML files allowed")
        
        # Read the uploaded content
        contents = await file.read()
        
        if filename_lower.endswith('.html') or filename_lower.endswith('.htm'):
            print(f"📥 Received HTML file: {file.filename}. Converting to DataFrame...")
            try:
                decoded_contents = contents.decode('utf-8')
            except UnicodeDecodeError:
                decoded_contents = contents.decode('latin-1')
            df = parse_takeout_html(decoded_contents)
            print(f"Parsed HTML into DataFrame with {len(df)} rows.")
        else:
            # Read CSV
            df = pd.read_csv(io.StringIO(contents.decode('utf-8')))
            print(f"📥 Received CSV: {file.filename} ({len(df)} rows)")
        
        # Validate required columns
        required_columns = {'Service', 'Action', 'Timestamp', 'Links'}
        if not required_columns.issubset(df.columns):
            raise HTTPException(
                status_code=400, 
                detail=f"Uploaded data must contain columns: {required_columns}. Found: {set(df.columns)}"
            )
        
        # Detect service type
        service_type = detect_service_type(df)
        print(f"🔍 Detected service type: {service_type}")
        
        # Process based on service type
        if service_type == 'youtube':
            if not api_key:
                raise HTTPException(
                    status_code=400,
                    detail="YouTube API key is required for YouTube data processing"
                )
            
            print("▶️ Processing YouTube data...")
            print("▶️ Processing YouTube data...")
            result_df, quota_exceeded = enrich_youtube_data(df, api_key)
            rows_stored = store_youtube_history(result_df)
            
            # Trigger asynchronous background processing (embeddings generation & interest classification)
            background_tasks.add_task(run_async_indexing_pipeline, DBState.engine)
            
            status = "warning" if quota_exceeded else "success"
            msg = (
                f"⚠️ YouTube API Quota Exceeded! Partially processed and saved {rows_stored} records. "
                "The database is indexing vectors in the background for the saved records. Please try again tomorrow."
                if quota_exceeded else
                f"✅ Processed {len(df)} YouTube records. Stored {rows_stored} to database. Indexing vectors and classifying interests in the background..."
            )
            
            return {
                "status": status,
                "service_type": "youtube",
                "rows_processed": len(df),
                "rows_stored": rows_stored,
                "indexing": True,
                "message": msg,
                "quota_exceeded": quota_exceeded,
                "columns_added": [
                    "video_id", "Video_Title", "Video_Description",
                    "Channel_Title", "Category_ID", "Category_Name",
                    "View_Count", "Like_Count"
                ]
            }
        
        else:  # search
            print("▶️ Processing Search data...")
            result_df = process_search_data(df)
            rows_stored = store_search_history(result_df)
            
            # Trigger asynchronous background processing (embeddings generation & interest classification)
            background_tasks.add_task(run_async_indexing_pipeline, DBState.engine)
            
            return {
                "status": "success",
                "service_type": "search",
                "rows_processed": len(df),
                "rows_stored": rows_stored,
                "indexing": True,
                "message": f"✅ Processed {len(df)} Search records. Stored {rows_stored} to database. Indexing vectors and classifying interests in the background...",
                "columns_added": ["Actual_Website"]
            }
    
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error processing file: {e}")
        raise HTTPException(status_code=500, detail=f"Error processing file: {str(e)}")

# ==========================================
# ENDPOINTS: AUTOMATED CHROME HISTORY INGESTION (NEW)
# ==========================================

@app.get("/chrome-profiles")
async def get_chrome_profiles():
    """
    Auto-discovers and returns available Chrome profiles on the local machine.
    """
    try:
        from parse_chrome_history import list_chrome_profiles
        profiles = list_chrome_profiles()
        return {"profiles": profiles}
    except Exception as e:
        print(f"❌ Failed to fetch Chrome profiles: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list Chrome profiles: {str(e)}")

@app.post("/ingest-chrome-local")
async def ingest_chrome_local(
    background_tasks: BackgroundTasks,
    profile: str = Form(default="Default"),
    days: int = Form(default=None)
):
    """
    Automatically parses local Chrome history and directly ingests it into Supabase database.
    """
    if not DBState.engine:
        raise HTTPException(
            status_code=400, 
            detail="Database not connected. Please connect to Supabase first."
        )
        
    try:
        import os
        from parse_chrome_history import parse_chrome_history
        
        print(f"📥 Automatically parsing local Chrome history for profile: {profile}...")
        
        # Parse history and generate temporary CSV files in the workspace './temp' folder
        yt_path, search_path = parse_chrome_history(
            profile=profile,
            days=days,
            output_dir="./temp"
        )
        
        search_rows_stored = 0
        rows_processed = 0
        
        # If Search history path is generated, read and store directly in the database
        if search_path and os.path.exists(search_path):
            print(f"📤 Storing Search/Browsing history in database from {search_path}...")
            search_df = pd.read_csv(search_path)
            if not search_df.empty:
                rows_processed = len(search_df)
                search_rows_stored = store_search_history(search_df)
        
        # Trigger vector embedding generation and log classification asynchronously
        background_tasks.add_task(run_async_indexing_pipeline, DBState.engine)
        
        return {
            "status": "success",
            "message": f"Successfully parsed and ingested Chrome history for profile '{profile}'!",
            "rows_processed": rows_processed,
            "rows_stored": search_rows_stored,
            "service_type": "search",
            "indexing": True
        }
        
    except Exception as e:
        print(f"❌ Automated Chrome Ingestion failed: {e}")
        raise HTTPException(status_code=500, detail=f"Automated ingestion failed: {str(e)}")

# ==========================================
# ENDPOINT: PROCESS CSV (Ported from main.py for backward compatibility)
# ==========================================
@app.post("/process-csv/")
async def process_csv(
    file: UploadFile = File(..., description="CSV file to process"),
    api_key: str = Form(default="", description="YouTube API Key (required for YouTube data)"),
    db_project_ref: str = Form(default="", description="Supabase Project Ref (for storing embeddings)"),
    db_password: str = Form(default="", description="Supabase Password"),
    db_host: str = Form(default="aws-1-ap-northeast-1.pooler.supabase.com", description="Supabase Host"),
    db_port: str = Form(default="6543", description="Supabase Port")
):
    """
    Process a CSV file based on its service type.
    
    - **file**: CSV file containing Service, Action, Timestamp, Links columns
    - **api_key**: YouTube API Key (required only for YouTube data)
    - **db_project_ref**: Supabase Project Ref (optional, for storing embeddings)
    - **db_password**: Supabase Password
    - **db_host**: Supabase Host
    - **db_port**: Supabase Port
    
    Returns the processed CSV file
    """
    try:
        # Validate and set Supabase credentials if provided
        if db_project_ref:
            print(f"🔐 Validating Supabase credentials...")
            success, message = validate_connection(db_project_ref, db_password, db_host, db_port)
            if not success:
                raise HTTPException(status_code=400, detail=f"Supabase connection failed: {message}")
            print(message)
            # Cache credentials for this session
            set_db_credentials(db_project_ref, db_password, db_host, db_port)
        
        # Read the uploaded CSV
        contents = await file.read()
        df = pd.read_csv(io.StringIO(contents.decode('utf-8')))
        
        # Validate required columns
        required_columns = {'Service', 'Action', 'Timestamp', 'Links'}
        if not required_columns.issubset(df.columns):
            raise HTTPException(
                status_code=400, 
                detail=f"CSV must contain columns: {required_columns}. Found: {set(df.columns)}"
            )
        
        # Detect service type
        service_type = detect_service_type(df)
        
        # Process based on service type
        if service_type == 'youtube':
            print("Routing to YouTube enrichment...")
            result_df, quota_exceeded = enrich_youtube_data(df, api_key)
            output_filename = "youtube_metadata_supervised.csv"
            headers = {
                "Content-Disposition": f"attachment; filename={output_filename}",
                "X-YouTube-Quota-Exceeded": "true" if quota_exceeded else "false"
            }
        else:  # search
            print("Routing to Search data processor...")
            result_df = process_search_data(df)
            output_filename = "parsed_Search_with_Websites.csv"
            headers = {
                "Content-Disposition": f"attachment; filename={output_filename}"
            }
        
        # Save to bytes
        output = io.BytesIO()
        result_df.to_csv(output, index=False)
        output.seek(0)
        
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers=headers
        )
    
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error processing CSV: {e}")
        raise HTTPException(status_code=500, detail=f"Error processing file: {str(e)}")

# ==========================================
# ENDPOINT 3: HEALTH CHECK (EXISTING - UNCHANGED)
# ==========================================
@app.get("/")
def read_root():
    """Health check endpoint"""
    return {
        "status": "FastAPI Server is running",
        "features": [
            "Hybrid RAG Agent ready",
            "CSV processing enabled" if CSV_PROCESSOR_AVAILABLE else "CSV processing disabled"
        ],
        "endpoints": {
            "POST /chat": "Chat with RAG agent about your history",
            "POST /upload-and-process-csv": "Upload and process CSV files",
            "POST /process-csv/": "Process CSV file and return processed version directly (backward-compatible)",
            "GET /": "This health check"
        }
    }

# ==========================================
# ENDPOINT 4: STATUS (NEW - HELPER)
# ==========================================
@app.get("/status")
def get_status():
    """Get detailed API status"""
    return {
        "api_version": "1.2",
        "csv_processor_available": CSV_PROCESSOR_AVAILABLE,
        "database_connected": DBState.engine is not None,
        "embeddings_loaded": True,
        "llm_available": DBState.llm_api_key is not None,
        "is_indexing": DBState.is_indexing,
        "indexing_message": DBState.indexing_message,
        "features": {
            "chat_with_agent": True,
            "csv_processing": CSV_PROCESSOR_AVAILABLE,
            "semantic_search": True,
            "sql_tools": True
        }
    }

# ==========================================
# ENDPOINTS 5 & 6: TAXONOMY DRIFT REVIEW & APPLY
# ==========================================

class ApplyDriftRequest(BaseModel):
    categories: list[str]

@app.get("/drift-analysis")
async def get_drift_analysis():
    """
    Scans for low-confidence classifications, clusters them using DeepSeek LLM,
    and returns suggested personal categories.
    """
    if not DBState.engine:
        raise HTTPException(status_code=400, detail="Database not connected.")
    if not DBState.llm_api_key:
        raise HTTPException(status_code=400, detail="LLM API key not configured. Please reconnect to Supabase with your LLM Key.")

    YT_THRESHOLD = 0.55
    SEARCH_THRESHOLD = 0.45

    try:
        with DBState.engine.connect() as conn:
            # Fetch "Unknown/Drift" Logs (Below confidence threshold)
            print("🔍 Scanning for logs below confidence thresholds...")
            unknown_logs_query = text("""
                WITH unclassified AS (
                    SELECT 
                        lc.id AS map_id, 
                        yh.video_title AS text, 
                        lc.confidence_score, 
                        'youtube' as source,
                        yh.id as raw_log_id
                    FROM log_classifications lc
                    JOIN youtube_history yh ON lc.youtube_log_id = yh.id
                    WHERE lc.youtube_log_id IS NOT NULL 
                      AND lc.confidence_score < :yt_thresh 
                      AND yh.drift_attempts < 2
                    
                    UNION ALL
                    
                    SELECT 
                        lc.id AS map_id, 
                        sh.actual_website AS text, 
                        lc.confidence_score, 
                        'search' as source,
                        sh.id as raw_log_id
                    FROM log_classifications lc
                    JOIN search_history sh ON lc.search_log_id = sh.id
                    WHERE lc.search_log_id IS NOT NULL 
                      AND lc.confidence_score < :search_thresh 
                      AND sh.drift_attempts < 2
                )
                SELECT * FROM unclassified ORDER BY confidence_score ASC LIMIT 50
            """)
            
            unknown_rows = conn.execute(unknown_logs_query, {"yt_thresh": YT_THRESHOLD, "search_thresh": SEARCH_THRESHOLD}).fetchall()
            
            if not unknown_rows:
                return {
                    "drift_found": False,
                    "suggested_categories": [],
                    "message": "✅ No taxonomy drift found! Your current interests cover your activity well."
                }
            
            # Cluster using LLM
            llm = ChatOpenAI(
                api_key=DBState.llm_api_key,
                base_url="https://api.deepseek.com",
                model="deepseek-chat",
                temperature=0.3
            )
            
            log_texts = [r[1] for r in unknown_rows if r[1]]
            
            from langchain_core.messages import SystemMessage
            prompt = f"""
            You are a highly precise taxonomy analyst maintaining a user interest taxonomy.
            The following digital activity logs did not match any of the user's existing interests.
            Your task is to analyze these logs and suggest 1 to 3 new broad category names representing genuine, intentional human learning or hobby interests (e.g., 'Home Repair', 'Time Management', 'Rust Programming').
            
            CRITICAL SAFETY RULES FOR NOISE ELIMINATION:
            1. Identify and skip any clusters dominated by ad-tracking pixels, redirects, system pings, web analytics, generic page loads, login pages, cookie walls, or accidental misclicks.
            2. If the logs are dominated by system noise, ads, or redirects, categorize them as "Noise" or "System/Ad Noise".
            3. Do NOT suggest categories for random ad URLs, tracking domains, or background network pings. Only suggest categories that a human would intentionally want to track as a personal topic of interest.
            
            Return ONLY a valid JSON list of strings representing the suggested categories (excluding any that are classified as "Noise" or "System/Ad Noise"). If everything is noise, return an empty list `[]`.
            Do not include markdown blocks, explanations, or any other characters.
            Example return: ["Home Repair", "Cybersecurity"]
            
            Logs to analyze:
            {json.dumps(log_texts[:30])}
            """
            
            response = llm.invoke([SystemMessage(content=prompt)])
            
            try:
                new_categories = json.loads(response.content.replace('```json', '').replace('```', '').strip())
                if not isinstance(new_categories, list):
                    new_categories = []
                # Backend safeguard: Filter out any categories containing noise keywords
                new_categories = [
                    c.strip() for c in new_categories 
                    if c and isinstance(c, str) and not any(w in c.lower() for w in ["noise", "ad ", "ads ", "redirect", "system", "cookie", "pixel", "misclick", "analytics", "tracking"])
                ]
            except Exception as e:
                print(f"❌ Failed to parse LLM response: {e}. Raw content: {response.content}")
                raise HTTPException(status_code=500, detail=f"LLM did not return valid JSON: {response.content}")
                
            return {
                "drift_found": True,
                "suggested_categories": new_categories,
                "drifted_logs_sample": [
                    {"text": r[1], "source": r[3], "confidence": r[2]} for r in unknown_rows[:5]
                ],
                "message": f"Found {len(unknown_rows)} low-confidence logs. Suggested categories to add: {new_categories}"
            }
            
    except Exception as e:
        print(f"❌ Error running drift analysis: {e}")
        raise HTTPException(status_code=500, detail=f"Drift analysis failed: {str(e)}")

@app.post("/apply-drift")
async def apply_drift(request: ApplyDriftRequest, background_tasks: BackgroundTasks):
    """
    Accepts new category suggestions, embeds and inserts them into Supabase,
    and triggers a background task to re-run classifications for affected low-confidence logs.
    """
    if not DBState.engine:
        raise HTTPException(status_code=400, detail="Database not connected.")
    
    if not request.categories:
        raise HTTPException(status_code=400, detail="No categories provided to apply.")

    YT_THRESHOLD = 0.55
    SEARCH_THRESHOLD = 0.45

    try:
        with DBState.engine.connect() as conn:
            # 1. Embed and insert categories
            print(f"Adding new categories: {request.categories}")
            for cat in request.categories:
                # Check if category already exists to avoid duplicate constraint errors
                exists = conn.execute(
                    text("SELECT 1 FROM interest_categories WHERE LOWER(category_name) = LOWER(:name)"),
                    {"name": cat}
                ).scalar()
                if exists:
                    continue
                    
                vec = embeddings.embed_query(cat)
                conn.execute(
                    text("""
                        INSERT INTO interest_categories (category_name, embedding, is_global, parent_id)
                        VALUES (:name, :vec, false, NULL)
                    """),
                    {"name": cat, "vec": str(vec)}
                )
            
            # 2. Fetch low-confidence log classifications to wipe
            print("Wiping low-confidence classifications so they can be re-categorized...")
            unknown_logs_query = text("""
                WITH unclassified AS (
                    SELECT 
                        lc.id AS map_id,
                        yh.id AS raw_log_id,
                        'youtube' AS source
                    FROM log_classifications lc
                    JOIN youtube_history yh ON lc.youtube_log_id = yh.id
                    WHERE lc.youtube_log_id IS NOT NULL 
                      AND lc.confidence_score < :yt_thresh
                      AND yh.drift_attempts < 2
                    
                    UNION ALL
                    
                    SELECT 
                        lc.id AS map_id,
                        sh.id AS raw_log_id,
                        'search' AS source
                    FROM log_classifications lc
                    JOIN search_history sh ON lc.search_log_id = sh.id
                    WHERE lc.search_log_id IS NOT NULL 
                      AND lc.confidence_score < :search_thresh
                      AND sh.drift_attempts < 2
                )
                SELECT map_id, raw_log_id, source FROM unclassified
            """)
            unknown_rows = conn.execute(unknown_logs_query, {"yt_thresh": YT_THRESHOLD, "search_thresh": SEARCH_THRESHOLD}).fetchall()
            map_ids = [r[0] for r in unknown_rows]
            
            # Increment drift_attempts for raw history logs to prevent looping forever
            yt_log_ids = [r[1] for r in unknown_rows if r[2] == 'youtube' and r[1] is not None]
            search_log_ids = [r[1] for r in unknown_rows if r[2] == 'search' and r[1] is not None]

            if yt_log_ids:
                if len(yt_log_ids) == 1:
                    conn.execute(text("UPDATE youtube_history SET drift_attempts = drift_attempts + 1 WHERE id = :id"), {"id": yt_log_ids[0]})
                else:
                    conn.execute(text("UPDATE youtube_history SET drift_attempts = drift_attempts + 1 WHERE id IN :ids"), {"ids": tuple(yt_log_ids)})

            if search_log_ids:
                if len(search_log_ids) == 1:
                    conn.execute(text("UPDATE search_history SET drift_attempts = drift_attempts + 1 WHERE id = :id"), {"id": search_log_ids[0]})
                else:
                    conn.execute(text("UPDATE search_history SET drift_attempts = drift_attempts + 1 WHERE id IN :ids"), {"ids": tuple(search_log_ids)})
            
            if map_ids:
                # Wipe these classifications so the next run of Phase 2 will classify them
                if len(map_ids) == 1:
                    conn.execute(text("DELETE FROM log_classifications WHERE id = :id"), {"id": map_ids[0]})
                else:
                    conn.execute(text("DELETE FROM log_classifications WHERE id IN :ids"), {"ids": tuple(map_ids)})
            
            conn.commit()

        # 3. Trigger background classification task to map the logs to the new categories
        background_tasks.add_task(run_async_indexing_pipeline, DBState.engine)
        
        return {
            "status": "success",
            "message": f"Successfully added categories: {request.categories}. Wiped low-confidence classifications and triggered background re-classification task."
        }
            
    except Exception as e:
        print(f"❌ Error applying drift: {e}")
        raise HTTPException(status_code=500, detail=f"Apply drift failed: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
