import urllib.parse
import re
import time
import requests
import pandas as pd
import numpy as np
from fastapi import HTTPException
from sqlalchemy import text
from .state import DBState

def is_noise_url(url):
    """
    Deterministically identifies if a URL is background system noise,
    ad trackers, redirects, telemetry, CDNs, or OAuth login loops.
    """
    if not url or not isinstance(url, str):
        return True
    
    url_lower = url.lower()
    
    # Common noise keywords/patterns in domain or path
    noise_patterns = [
        # Ads
        r'doubleclick\.net', r'googleads', r'adsystem', r'adnxs', r'adservice', r'pagead', r'taboola', r'outbrain', r'criteo',
        # Analytics / Telemetry
        r'google-analytics\.com', r'analytics', r'telemetry', r'segment\.io', r'mixpanel', r'hotjar', r'sentry\.io', r'datadoghq',
        # Pixels / Facebook tracking
        r'/tr/\?id=', r'facebook\.net/tr', r'ping', r'pixel', r'telemetry',
        # Auth / Login redirects
        r'/oauth', r'/signin', r'/login', r'/auth/callback', r'accounts\.google\.com', r'login\.microsoftonline\.com',
        # CDNs and static asset domains
        r'cloudfront\.net', r'fastly\.net', r'gstatic\.com', r'googleapis\.com', r'cdnjs\.cloudflare\.com', r'favicon'
    ]
    
    for pattern in noise_patterns:
        if re.search(pattern, url_lower):
            return True
            
    return False


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

def normalize_timestamp_str(ts):
    if not ts:
        return ""
    if hasattr(ts, 'strftime'):
        return ts.strftime('%Y-%m-%d %H:%M:%S')
    try:
        parsed = pd.to_datetime(ts)
        if pd.notna(parsed):
            return parsed.strftime('%Y-%m-%d %H:%M:%S')
    except Exception:
        pass
    return str(ts)

def extract_video_id(links):
    if pd.isna(links):
        return None
    url_str = str(links)
    match = re.search(r'(?:v=|\/shorts\/|\/youtu\.be\/|embed\/)([a-zA-Z0-9_-]{11})', url_str)
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
        return df, False
    
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
    """Extracts actual website domains from search data and filters out noise URLs."""
    print(f"Processing Search data with {len(df)} rows...")
    # Drop rows that are noise URLs (ads, trackers, redirects, telemetry, etc.)
    df = df[~df['Links'].apply(is_noise_url)]
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

def clean_url_to_semantic_text(url):
    """
    Parses and cleans raw URLs into optimized semantic natural language strings.
    Strips protocols, subdomains (like www), query parameters, and splits path slugs
    by common separators (-, _, /, .) into a clean descriptive sentence.
    """
    if not url or not isinstance(url, str):
        return ""
        
    try:
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
                
            # Remove any trailing extension (e.g. html, php)
            seg_text = re.sub(r'\.(html|htm|php|asp|aspx)$', '', segment, flags=re.IGNORECASE)
            # Replace common separators with spaces
            seg_text = re.sub(r'[-_\.\+]', ' ', seg_text)
            seg_text = ' '.join(seg_text.split())
            if seg_text:
                cleaned_segments.append(seg_text)
                
        if not cleaned_segments:
            return domain
            
        return f"{domain} / " + " / ".join(cleaned_segments)
    except Exception:
        return url

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
            batch_size = 500
            
            # Local deduplication (avoid processing duplicates within the upload batch)
            unique_df_rows = []
            seen_in_upload = set()
            for _, row in df.iterrows():
                link = row.get('Links')
                ts = normalize_timestamp_str(row.get('Timestamp'))
                if not link:
                    continue
                key = (link, ts)
                if key in seen_in_upload:
                    continue
                seen_in_upload.add(key)
                unique_df_rows.append(row)
                
            insert_query = text("""
                INSERT INTO youtube_history 
                (links, video_title, channel_title, view_count, like_count, 
                 category_name, timestamp, service)
                VALUES (:links, :title, :channel, :views, :likes, :category, 
                        :timestamp, 'YouTube')
            """)
            
            def log_youtube_error(item, err):
                print(f"❌ Failed to insert YouTube row {item.get('links')}: {err}")
                
            # Process in localized chunks of 500
            for k in range(0, len(unique_df_rows), batch_size):
                chunk_rows = unique_df_rows[k:k + batch_size]
                chunk_links = [row.get('Links') for row in chunk_rows]
                
                # Fetch existing links/timestamps in database only for the active chunk
                with DBState.engine.connect() as conn:
                    placeholders = ", ".join(f":l{i}" for i in range(len(chunk_links)))
                    query = text(f"SELECT links, timestamp FROM youtube_history WHERE links IN ({placeholders})")
                    params = {f"l{i}": link for i, link in enumerate(chunk_links)}
                    existing_records_set = {
                        (row[0], normalize_timestamp_str(row[1])) 
                        for row in conn.execute(query, params).fetchall()
                    }
                
                # Prepare insert chunk by filtering out database duplicates
                insert_batch = []
                for row in chunk_rows:
                    link = row.get('Links')
                    ts = normalize_timestamp_str(row.get('Timestamp'))
                    if (link, ts) in existing_records_set:
                        continue
                    
                    insert_batch.append({
                        "links": link,
                        "title": row.get('Video_Title'),
                        "channel": row.get('Channel_Title'),
                        "views": safe_int(row.get('View_Count')),
                        "likes": safe_int(row.get('Like_Count')),
                        "category": row.get('Category_Name'),
                        "timestamp": row.get('Timestamp')
                    })
                
                if insert_batch:
                    rows_inserted += insert_chunk_recursive(DBState.engine, insert_query, insert_batch, log_youtube_error)
            
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
            raise e

def store_search_history(df):
    """Insert processed search data into database in high-performance batches"""
    from sqlalchemy.exc import OperationalError
    from sqlalchemy import inspect
    
    df = df.where(pd.notnull(df), None)
    
    # Dynamic check: Does page_title exist in search_history?
    has_page_title = False
    try:
        inspector = inspect(DBState.engine)
        columns = [col['name'] for col in inspector.get_columns('search_history')]
        has_page_title = 'page_title' in columns
    except Exception as e:
        print(f"⚠️ Warning checking search_history columns: {e}. Defaulting to has_page_title = False")
        
    max_retries = 3
    for attempt in range(max_retries):
        try:
            rows_inserted = 0
            batch_size = 500
            
            # Local deduplication (avoid processing duplicates within the upload batch)
            unique_df_rows = []
            seen_in_upload = set()
            for _, row in df.iterrows():
                link = row.get('Links')
                ts = normalize_timestamp_str(row.get('Timestamp'))
                action = row.get('Action')
                
                key = (link, ts) if link else (action, ts)
                if key in seen_in_upload:
                    continue
                seen_in_upload.add(key)
                unique_df_rows.append(row)
                
            if has_page_title:
                insert_query = text("""
                    INSERT INTO search_history 
                    (links, actual_website, timestamp, service, page_title, action)
                    VALUES (:links, :website, :timestamp, 'Search', :page_title, :action)
                """)
            else:
                insert_query = text("""
                    INSERT INTO search_history 
                    (links, actual_website, timestamp, service, action)
                    VALUES (:links, :website, :timestamp, 'Search', :action)
                """)
            
            def log_search_error(item, err):
                print(f"❌ Failed to insert Search row {item.get('links') or item.get('action')}: {err}")
                
            # Process in localized chunks of 500
            for k in range(0, len(unique_df_rows), batch_size):
                chunk_rows = unique_df_rows[k:k + batch_size]
                chunk_keys = []
                for row in chunk_rows:
                    link = row.get('Links')
                    action = row.get('Action')
                    chunk_keys.append(link if link else action)
                
                # Fetch existing keys/timestamps in database only for the active chunk
                with DBState.engine.connect() as conn:
                    placeholders = ", ".join(f":k{i}" for i in range(len(chunk_keys)))
                    
                    if has_page_title:
                        query = text(f"""
                            SELECT links, action, timestamp 
                            FROM search_history 
                            WHERE links IN ({placeholders}) OR action IN ({placeholders})
                        """)
                    else:
                        query = text(f"""
                            SELECT links, timestamp 
                            FROM search_history 
                            WHERE links IN ({placeholders})
                        """)
                        
                    params = {f"k{i}": key for i, key in enumerate(chunk_keys)}
                    
                    if has_page_title:
                        existing_records_set = {
                            (row[0] if row[0] else row[1], normalize_timestamp_str(row[2])) 
                            for row in conn.execute(query, params).fetchall()
                        }
                    else:
                        existing_records_set = {
                            (row[0], normalize_timestamp_str(row[1])) 
                            for row in conn.execute(query, params).fetchall()
                        }
                
                # Prepare insert chunk by filtering out database duplicates
                insert_batch = []
                for row in chunk_rows:
                    link = row.get('Links')
                    ts = normalize_timestamp_str(row.get('Timestamp'))
                    action = row.get('Action')
                    
                    key = link if link else action
                    if (key, ts) in existing_records_set:
                        continue
                    
                    item = {
                        "links": link,
                        "website": row.get('Actual_Website'),
                        "timestamp": row.get('Timestamp'),
                        "action": action
                    }
                    if has_page_title:
                        item["page_title"] = row.get('Page_Title')
                        
                    insert_batch.append(item)
                
                if insert_batch:
                    rows_inserted += insert_chunk_recursive(DBState.engine, insert_query, insert_batch, log_search_error)
            
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
            raise e
