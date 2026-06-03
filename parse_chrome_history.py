#!/usr/bin/env python
"""
Chrome History Parser

Reads Chrome's local SQLite History database (using a safe copy),
extracts browsing history with page titles, and outputs CSV files
compatible with the Google Takeout RAG ingestion pipeline.

Key Features:
- Copies the History file first so Chrome can stay open
- Preserves page titles (critical for identifying chat topics, search queries, specific pages visited, etc.)
- Splits output into YouTube history and Search/Browsing history CSVs
- Handles Google redirect URLs and extracts actual website domains

Usage:
    python parse_chrome_history.py
    python parse_chrome_history.py --profile "Profile 1"
    python parse_chrome_history.py --days 90
    python parse_chrome_history.py --output-dir ./exports
"""

import sqlite3
import shutil
import os
import sys
import re
import argparse
import tempfile
import urllib.parse
from datetime import datetime, timedelta

import pandas as pd


# Chrome stores timestamps as microseconds since 1601-01-01 00:00:00 UTC
CHROME_EPOCH = datetime(1601, 1, 1)


def get_chrome_history_path(profile="Default"):
    """
    Returns the path to Chrome's History SQLite database.
    Supports Windows, macOS, and Linux.
    """
    if sys.platform == "win32":
        base = os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\User Data")
    elif sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support/Google/Chrome")
    else:  # Linux
        base = os.path.expanduser("~/.config/google-chrome")
    
    return os.path.join(base, profile, "History")


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


def chrome_time_to_datetime(chrome_timestamp):
    """Converts Chrome's microsecond timestamp (since 1601-01-01) to Python datetime."""
    if chrome_timestamp is None or chrome_timestamp == 0:
        return None
    try:
        return CHROME_EPOCH + timedelta(microseconds=chrome_timestamp)
    except (OverflowError, ValueError):
        return None


def extract_google_search_query(url):
    """Extracts the search query from a Google Search URL."""
    try:
        parsed = urllib.parse.urlparse(url)
        if 'google.' in parsed.netloc and '/search' in parsed.path:
            params = urllib.parse.parse_qs(parsed.query)
            query = params.get('q', [''])[0]
            if query:
                return query
    except Exception:
        pass
    return None


def extract_actual_website(url):
    """Extracts the actual website domain from a URL, handling Google redirects."""
    if not url:
        return None
    try:
        parsed = urllib.parse.urlparse(url)
        
        # Handle Google redirect URLs (e.g., https://www.google.com/url?q=...)
        if 'google.' in parsed.netloc and parsed.path == '/url':
            params = urllib.parse.parse_qs(parsed.query)
            if 'q' in params:
                target_url = params['q'][0]
                target_parsed = urllib.parse.urlparse(target_url)
                return target_parsed.netloc
        
        return parsed.netloc
    except Exception:
        return "Parsing Error"


def clean_url_to_semantic_text(url):
    """
    Parses and cleans raw URLs into optimized semantic natural language strings.
    Strips protocols, subdomains (like www), query parameters, and splits path slugs
    by common separators (-, _, /, .) into a clean descriptive sentence.
    
    Example:
    'https://github.com/langchain-ai/langgraph/issues/123?q=vector'
    becomes:
    'github.com / langchain ai / langgraph / issues'
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


def list_chrome_profiles():
    """Lists available Chrome profiles on this system."""
    if sys.platform == "win32":
        base = os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\User Data")
    elif sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support/Google/Chrome")
    else:
        base = os.path.expanduser("~/.config/google-chrome")
    
    profiles = []
    if os.path.exists(base):
        for item in os.listdir(base):
            item_path = os.path.join(base, item)
            if os.path.isdir(item_path) and os.path.exists(os.path.join(item_path, "History")):
                profiles.append(item)
    return profiles


def parse_chrome_history(profile="Default", days=None, output_dir="."):
    """
    Main function: copies Chrome's History DB, parses it, and outputs CSVs.
    
    Args:
        profile: Chrome profile folder name (default: "Default")
        days: Only include history from the last N days (None = all history)
        output_dir: Directory to save output CSV files
    
    Returns:
        Tuple of (youtube_csv_path, search_csv_path) or (None, None) on failure
    """
    # 1. Locate Chrome's History file
    history_path = get_chrome_history_path(profile)
    
    if not os.path.exists(history_path):
        print(f"❌ Chrome History file not found at: {history_path}")
        available = list_chrome_profiles()
        if available:
            print(f"   Available Chrome profiles:")
            for p in available:
                print(f"     - {p}")
            print(f"\n   Try: python parse_chrome_history.py --profile \"{available[0]}\"")
        return None, None
    
    # 2. Copy the file to avoid Chrome's lock
    print(f"📋 Copying Chrome History database (to avoid lock)...")
    temp_dir = tempfile.mkdtemp()
    temp_history = os.path.join(temp_dir, "History_copy")
    
    try:
        shutil.copy2(history_path, temp_history)
        print(f"   ✅ Copied successfully")
    except PermissionError:
        print("❌ Permission denied. Try running as administrator.")
        return None, None
    except Exception as e:
        print(f"❌ Failed to copy: {e}")
        return None, None
    
    # 3. Open and query the SQLite database
    print(f"🔍 Reading Chrome history...")
    conn = sqlite3.connect(temp_history)
    
    # Build the time filter
    time_filter = ""
    params = {}
    if days:
        cutoff_dt = datetime.utcnow() - timedelta(days=days)
        cutoff_chrome = int((cutoff_dt - CHROME_EPOCH).total_seconds() * 1_000_000)
        time_filter = "AND v.visit_time >= :cutoff"
        params["cutoff"] = cutoff_chrome
    
    query = f"""
        SELECT 
            u.url,
            u.title,
            v.visit_time
        FROM visits v
        JOIN urls u ON v.url = u.id
        WHERE u.url NOT LIKE 'chrome://%'
          AND u.url NOT LIKE 'chrome-extension://%'
          AND u.url NOT LIKE 'about:%'
          AND u.url NOT LIKE 'edge://%'
          AND u.url NOT LIKE 'file://%'
          AND u.url NOT LIKE 'devtools://%'
          {time_filter}
        ORDER BY v.visit_time ASC
    """
    
    try:
        cursor = conn.execute(query, params)
        rows = cursor.fetchall()
    except Exception as e:
        print(f"❌ Failed to query database: {e}")
        conn.close()
        return None, None
    finally:
        conn.close()
    
    # Clean up temp file
    try:
        os.remove(temp_history)
        os.rmdir(temp_dir)
    except Exception:
        pass
    
    print(f"   📊 Found {len(rows)} history entries")
    
    if not rows:
        print("⚠️ No history entries found.")
        return None, None
    
    # 4. Process and categorize entries
    youtube_entries = []
    search_entries = []
    
    for url, title, visit_time in rows:
        if is_noise_url(url):
            continue
        dt = chrome_time_to_datetime(visit_time)
        if dt is None:
            continue
        
        timestamp_str = dt.strftime('%Y-%m-%dT%H:%M:%SZ')
        title = (title or "").strip()
        if not title:
            title = clean_url_to_semantic_text(url)
        
        # Categorize by URL
        if 'youtube.com/watch' in url:
            # YouTube video watch
            youtube_entries.append({
                'Service': 'YouTube',
                'Action': 'WATCH',
                'Timestamp': timestamp_str,
                'Links': url,
                'Page_Title': title
            })
        elif re.search(r'google\.\w+/search', url):
            # Google Search query
            search_query = extract_google_search_query(url)
            action = f"Searched for {search_query}" if search_query else "SEARCH"
            search_entries.append({
                'Service': 'Search',
                'Action': action,
                'Timestamp': timestamp_str,
                'Links': url,
                'Page_Title': title,
                'Actual_Website': extract_actual_website(url)
            })
        else:
            # General browsing (includes grok.com, stackoverflow.com, etc.)
            search_entries.append({
                'Service': 'Search',
                'Action': 'CLICK',
                'Timestamp': timestamp_str,
                'Links': url,
                'Page_Title': title,
                'Actual_Website': extract_actual_website(url)
            })
    
    # 5. Save to CSVs
    os.makedirs(output_dir, exist_ok=True)
    
    yt_path = None
    search_path = None
    
    if youtube_entries:
        yt_df = pd.DataFrame(youtube_entries)
        yt_path = os.path.join(output_dir, "chrome_youtube_history.csv")
        yt_df.to_csv(yt_path, index=False)
        print(f"\n  YouTube history: {len(yt_df)} entries -> {yt_path}")
    else:
        print(f"\n  No YouTube entries found in Chrome history")
    
    if search_entries:
        search_df = pd.DataFrame(search_entries)
        search_path = os.path.join(output_dir, "chrome_search_history.csv")
        search_df.to_csv(search_path, index=False)
        print(f"  Search/Browsing history: {len(search_df)} entries -> {search_path}")
        
        # Print domain summary
        print(f"\n📊 Top 15 most visited domains:")
        top_domains = search_df['Actual_Website'].value_counts().head(15)
        for domain, count in top_domains.items():
            print(f"   {domain}: {count} visits")
        
        # Highlight top domains and their unique page titles (completely generic!)
        print("\n🌐 Overview of unique pages visited by top domains:")
        # Filter for domains with non-empty page titles to get meaningful results
        has_title = search_df['Page_Title'].dropna().str.strip().str.len() > 0
        top_visited_with_titles = search_df[has_title]['Actual_Website'].value_counts().head(5)
        for domain, count in top_visited_with_titles.items():
            domain_df = search_df[(search_df['Actual_Website'] == domain) & has_title]
            unique_titles = domain_df['Page_Title'].dropna().unique()
            print(f"   • {domain} ({count} visits with titles):")
            print(f"     Unique page titles/topics ({len(unique_titles)}):")
            for t in unique_titles[:5]:  # Show up to 5 representative page titles
                if t.strip():
                    print(f"       - {t}")
    else:
        print(f"\n⚠️ No Search/Browsing entries found in Chrome history")
    
    # 6. Print overall summary
    total = len(youtube_entries) + len(search_entries)
    print(f"\n{'-' * 50}")
    print(f"  Total entries exported: {total}")
    print(f"  YouTube:               {len(youtube_entries)}")
    print(f"  Search/Browsing:       {len(search_entries)}")
    if days:
        print(f"  Time range:            Last {days} days")
    else:
        # Show actual date range
        all_timestamps = [e['Timestamp'] for e in youtube_entries + search_entries]
        if all_timestamps:
            print(f"  Date range:            {all_timestamps[0][:10]} to {all_timestamps[-1][:10]}")
    print(f"{'-' * 50}")
    
    return yt_path, search_path


def main():
    parser = argparse.ArgumentParser(
        description="Parse Chrome's local browser history into CSV files for the RAG pipeline"
    )
    parser.add_argument(
        "--profile", 
        default="Default",
        help="Chrome profile folder name (default: 'Default'). Use 'Profile 1', 'Profile 2', etc. for additional profiles."
    )
    parser.add_argument(
        "--days", 
        type=int, 
        default=None,
        help="Only include history from the last N days (default: all history)"
    )
    parser.add_argument(
        "--output-dir", 
        default=".",
        help="Directory to save output CSV files (default: current directory)"
    )
    parser.add_argument(
        "--list-profiles",
        action="store_true",
        help="List available Chrome profiles and exit"
    )
    
    args = parser.parse_args()
    
    # Handle --list-profiles
    if args.list_profiles:
        profiles = list_chrome_profiles()
        if profiles:
            print("Available Chrome profiles:")
            for p in profiles:
                print(f"  - {p}")
        else:
            print("No Chrome profiles found on this system.")
        return
    
    print("\n" + "=" * 60)
    print("  Chrome History Parser -> RAG Pipeline CSV")
    print("=" * 60 + "\n")
    
    yt_path, search_path = parse_chrome_history(
        profile=args.profile,
        days=args.days,
        output_dir=args.output_dir
    )
    
    if yt_path or search_path:
        print(f"\n{'=' * 60}")
        print(f"  ✅ Export complete!")
        print(f"\n  Next steps:")
        if search_path:
            print(f"  1. Upload '{os.path.basename(search_path)}' via the Flutter app")
            print(f"     (This contains your browsing visits and AI chat topics with page titles)")
        if yt_path:
            print(f"  2. Upload '{os.path.basename(yt_path)}' via the Flutter app")
            print(f"     (Requires YouTube API key for enrichment)")
        print(f"{'=' * 60}\n")
    else:
        print("\n❌ Export failed. Check the errors above.")


if __name__ == "__main__":
    main()
