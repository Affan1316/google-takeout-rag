import pandas as pd
import re
import requests
import time
import os

API_KEY = os.environ.get('YOUTUBE_API_KEY')

def fetch_dynamic_categories():
    """Fetches up-to-date YouTube categories directly from the API."""
    if not API_KEY:
        print("Warning: YOUTUBE_API_KEY not found in environment variables. Category fetching will fail.")
        return {}
        
    print("Fetching active YouTube categories...")
    url = f"https://www.googleapis.com/youtube/v3/videoCategories?part=snippet&regionCode=US&key={API_KEY}"
    try:
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            return {item['id']: item['snippet']['title'] for item in data.get('items', [])}
        else:
            print("Warning: Could not fetch categories. Falling back to unknown.")
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
        response = requests.get(url, params=params)

        if response.status_code == 200:
            return response
        elif response.status_code == 403:
            # 403 can represent Quota Exceeded or other authorization issues.
            # Inspect the response to see if it is a hard quota exhaustion.
            try:
                err_json = response.json()
                errors = err_json.get('error', {}).get('errors', [])
                reasons = [e.get('reason') for e in errors]
                if 'quotaExceeded' in reasons:
                    print("\n❌ YouTube API Quota Exceeded! Exiting ingestion pipeline to save progress...")
                    raise YouTubeQuotaExceededException("YouTube API quota exceeded.")
            except (ValueError, TypeError, AttributeError):
                pass
            
            # If not a specific quotaExceeded reason, treat it as a transient key validation or access retry
            wait_time = (2 ** attempt) + 1
            print(f"⚠️ Warning (Status 403). Retrying in {wait_time} seconds...")
            time.sleep(wait_time)
            
        elif response.status_code == 429: # 429: Too Many Requests
            wait_time = (2 ** attempt) + 1 # Waits 2s, 3s, 5s...
            print(f"⚠️ Rate limited (Status 429). Retrying in {wait_time} seconds...")
            time.sleep(wait_time)
        else:
            print(f"❌ Error {response.status_code}: {response.text}")
            return None

    print("❌ Max retries reached. Skipping chunk.")
    return None

def extract_video_id(links):
    if pd.isna(links):
        return None
    match = re.search(r'watch\?v=([a-zA-Z0-9_-]{11})', str(links))
    return match.group(1) if match else None

def main():
    input_filename = 'parsed_YouTube.csv'

    # 1. Read Data directly from Colab files
    print(f"Loading {input_filename}...")
    try:
        df = pd.read_csv(input_filename)
    except FileNotFoundError:
        print(f"❌ Error: Could not find '{input_filename}'. Please ensure it is in the main folder in the Colab sidebar.")
    # Extract Video IDs
    df['video_id'] = df['Links'].apply(extract_video_id)
    unique_video_ids = df['video_id'].dropna().unique().tolist()
    print(f"Found {len(unique_video_ids)} unique videos to process.\n")
    
    if not API_KEY:
        print("❌ Error: YOUTUBE_API_KEY environment variable is missing. Cannot fetch metadata from YouTube.")
        return

    # 2. Get Dynamic Categories
    categories_map = fetch_dynamic_categories()

    # 3. Fetch Metadata in Batches with Retry Logic
    YOUTUBE_API_URL = 'https://www.googleapis.com/youtube/v3/videos'
    metadata_list = []
    chunk_size = 50

    print("\nFetching metadata from YouTube API in batches...")
    try:
        for i in range(0, len(unique_video_ids), chunk_size):
            chunk_ids = unique_video_ids[i:i + chunk_size]
            params = {
                'part': 'snippet,statistics',
                'id': ','.join(chunk_ids),
                'key': API_KEY
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
        print("⚠️ Saving already processed videos...")

    # 4. Merge and Output
    print("\nMerging metadata with original dataset...")
    metadata_df = pd.DataFrame(metadata_list)

    if not metadata_df.empty:
        # Merge preserving the original rows
        df_enriched = pd.merge(df, metadata_df, on='video_id', how='left')

        # Clean title text just in case
        df_enriched['Video_Title'] = df_enriched['Video_Title'].astype(str).str.replace(r'\s+', ' ', regex=True).str.strip()

        output_file = 'youtube_metadata_supervised.csv'
        df_enriched.to_csv(output_file, index=False)
        print(f"✅ Success! Enriched data saved to '{output_file}'.")
    else:
        print("⚠️ No metadata generated. Please check your API quota.")

if __name__ == "__main__":
    main()