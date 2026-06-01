import pandas as pd
from bs4 import BeautifulSoup
import urllib.parse
from datetime import datetime
import re
import argparse
import sys

def parse_takeout_html(html_content):
    """
    Parses Google Takeout My Activity HTML (both YouTube watch history and Google search history)
    into a structured Pandas DataFrame.
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    entries = []
    
    # Google Takeout uses class 'outer-cell' for each entry
    cells = soup.find_all('div', class_='outer-cell')
    
    # Fallback to 'content-cell' if outer-cell is not found
    if not cells:
        cells = soup.find_all('div', class_='content-cell')
        
    print(f"Parsing {len(cells)} activity cells from HTML...")
        
    for cell in cells:
        # 1. Identify Service
        service = "Unknown"
        header = cell.find('div', class_='header-cell')
        if header:
            service = header.get_text(strip=True)
        else:
            caption = cell.find('span', class_='mdl-typography--caption')
            if caption:
                caption_text = caption.get_text(strip=True)
                if "YouTube" in caption_text:
                    service = "YouTube"
                elif "Search" in caption_text:
                    service = "Search"
                    
        if service == "Unknown":
            bold_text = cell.find('b')
            if bold_text:
                service = bold_text.get_text(strip=True)

        # Normalize service names
        if "youtube" in service.lower():
            service = "YouTube"
        elif "search" in service.lower():
            service = "Search"
        
        # 2. Extract Content details
        content_cell = cell.find('div', class_='content-cell')
        if not content_cell:
            content_cell = cell
            
        links = content_cell.find_all('a')
        
        action = "CLICK"
        url = None
        
        # Extract cell text excluding product caption if present
        cell_text = content_cell.get_text(" | ", strip=True)
        caption = content_cell.find('span', class_='mdl-typography--caption')
        if caption:
            caption_text = caption.get_text(" | ", strip=True)
            cell_text = cell_text.replace(caption_text, "").strip(" | ")
            
        if links:
            first_link = links[0]
            url = first_link.get('href')
            link_text = first_link.get_text(strip=True)
            
            # YouTube Watch History
            if "youtube.com/watch" in url:
                service = "YouTube"
                action = "WATCH"
            # Search History
            elif "google.com/search" in url or "google.com/url" in url:
                service = "Search"
                if "google.com/search" in url:
                    parsed_url = urllib.parse.urlparse(url)
                    query = urllib.parse.parse_qs(parsed_url.query).get('q', [''])[0]
                    action = f"Searched for {query}" if query else "Searched for " + link_text
                else:
                    action = "CLICK"
            else:
                if "Searched for" in cell_text:
                    action = "Searched for " + link_text
                else:
                    action = "CLICK"
        else:
            action = cell_text
            
        # 3. Extract Timestamp
        # Timestamps are typically the last non-caption stripped string inside the cell
        chunks = list(content_cell.stripped_strings)
        if caption:
            caption_strings = list(caption.stripped_strings)
            chunks = [c for c in chunks if c not in caption_strings]
            
        timestamp = None
        for chunk in reversed(chunks):
            # Google timestamps usually contain year and time (HH:MM)
            if re.search(r'\d{4}', chunk) and re.search(r'\d{1,2}:\d{2}', chunk):
                try:
                    # Clean up common unrecognized timezone abbreviations (e.g. PDT, PST, BST, EDT, EST, IST)
                    # to prevent deprecation or parsing warnings
                    clean_chunk = re.sub(r'\s+[A-Z]{3,4}$', '', chunk)
                    parsed_date = pd.to_datetime(clean_chunk, errors='coerce')
                    if pd.notna(parsed_date):
                        timestamp = parsed_date.strftime('%Y-%m-%dT%H:%M:%SZ')
                        break
                except Exception:
                    pass
                    
        if not timestamp:
            timestamp = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
            
        entries.append({
            'Service': service,
            'Action': action,
            'Timestamp': timestamp,
            'Links': url
        })
        
    return pd.DataFrame(entries)

def main():
    parser = argparse.ArgumentParser(description="Convert Google Takeout HTML activity to clean CSV format")
    parser.add_argument("-i", "--input", required=True, help="Path to the Google Takeout 'My Activity.html' file")
    parser.add_argument("-o", "--output", required=True, help="Path to save the converted CSV file")
    
    args = parser.parse_args()
    
    try:
        print(f"Reading input file: {args.input}...")
        with open(args.input, "r", encoding="utf-8") as f:
            html_content = f.read()
            
        df = parse_takeout_html(html_content)
        
        if df.empty:
            print("[Warning] No activity items found in the HTML file.")
            sys.exit(1)
            
        print(f"Successfully extracted {len(df)} records!")
        print(f"Saving to CSV: {args.output}...")
        df.to_csv(args.output, index=False)
        print("[Success] Converted Google Takeout HTML to CSV!")
        
    except Exception as e:
        print(f"[Error] {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
