import pandas as pd
from bs4 import BeautifulSoup
import urllib.parse
from datetime import datetime
import re
import argparse
import sys

# Localization month translation map for European languages to English
MONTH_MAP = {
    # French
    'janvier': 'january', 'février': 'february', 'mars': 'march', 'avril': 'april',
    'mai': 'may', 'juin': 'june', 'juillet': 'july', 'août': 'august',
    'septembre': 'september', 'octobre': 'october', 'novembre': 'november', 'décembre': 'december',
    'janv.': 'jan', 'févr.': 'feb', 'avr.': 'apr', 'juil.': 'jul', 'sept.': 'sep', 'déc.': 'dec',
    # Spanish
    'enero': 'january', 'febrero': 'february', 'marzo': 'march', 'abril': 'april',
    'mayo': 'may', 'junio': 'june', 'julio': 'july', 'agosto': 'august',
    'septiembre': 'september', 'octubre': 'october', 'noviembre': 'november', 'diciembre': 'december',
    'ene.': 'jan', 'feb.': 'feb', 'mar.': 'mar', 'abr.': 'apr', 'ago.': 'aug', 'dic.': 'dec',
    # German
    'januar': 'january', 'februar': 'february', 'märz': 'march', 'mai': 'may',
    'juni': 'june', 'juli': 'july', 'oktober': 'october', 'dezember': 'december',
    'jan': 'jan', 'feb': 'feb', 'mrz': 'mar', 'apr': 'apr', 'jun': 'jun', 'jul': 'jul',
    'aug': 'aug', 'sep': 'sep', 'okt': 'oct', 'nov': 'nov', 'dez': 'dec',
    # Portuguese / Italian
    'maggio': 'may', 'giugno': 'june', 'luglio': 'july', 'settembre': 'september',
    'ottobre': 'october', 'novembre': 'november', 'dicembre': 'december',
    'junho': 'june', 'julho': 'july', 'outubro': 'october', 'dezembro': 'december'
}

def clean_and_parse_localized_date(date_str):
    """
    Cleans up localized timezone abbreviations and translates non-English month names
    so pandas can successfully parse the timestamp.
    """
    if not date_str:
        return None
    # 1. Clean timezone suffixes (e.g. UTC, GMT+5, PDT, CEST, etc.)
    # Strip uppercase timezone labels and time offsets from the end
    cleaned = re.sub(r'\s+(?:[A-Z]{3,4}|GMT[+-]\d+|UTC[+-]\d+|\d+:[0-9]{2})$', '', date_str.strip())
    # Strip standard localized connector words
    cleaned = re.sub(r'\s+à\s+', ' ', cleaned)
    cleaned = re.sub(r'\s+um\s+', ' ', cleaned)
    cleaned = re.sub(r'\s+at\s+', ' ', cleaned)
    cleaned = re.sub(r'\s+o\s+', ' ', cleaned)
    
    # 2. Map localized months
    words = cleaned.split()
    translated_words = []
    for w in words:
        clean_w = w.lower().rstrip(',.')
        if clean_w in MONTH_MAP:
            translated_words.append(MONTH_MAP[clean_w])
        else:
            translated_words.append(w)
    translated_str = ' '.join(translated_words)
    
    try:
        parsed_date = pd.to_datetime(translated_str, errors='coerce')
        if pd.notna(parsed_date):
            return parsed_date.strftime('%Y-%m-%dT%H:%M:%SZ')
    except Exception:
        pass
    return None

def parse_takeout_html(html_content):
    """
    Parses Google Takeout My Activity HTML (both YouTube watch history and Google search history)
    into a structured Pandas DataFrame. Supports non-English locales and YouTube Shorts/Share links.
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

        # Normalize localized service names
        service_lower = service.lower()
        if "youtube" in service_lower:
            service = "YouTube"
        elif any(kw in service_lower for kw in ["search", "búsqueda", "recherche", "suche", "ricerca", "pesquisa"]):
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
            
            # YouTube Link Detection (watch, shorts, youtu.be, embed)
            is_youtube_link = False
            if url:
                if "youtube.com/watch" in url or "youtube.com/shorts" in url or "youtu.be" in url or "youtube.com/embed" in url:
                    is_youtube_link = True
            
            if is_youtube_link:
                service = "YouTube"
                action = "WATCH"
            # Search History
            elif url and ("google." in url and ("/search" in url or "/url" in url)):
                service = "Search"
                if "/search" in url:
                    parsed_url = urllib.parse.urlparse(url)
                    query = urllib.parse.parse_qs(parsed_url.query).get('q', [''])[0]
                    action = f"Searched for {query}" if query else "Searched for " + link_text
                else:
                    action = "CLICK"
            else:
                cell_lower = cell_text.lower()
                if any(p in cell_lower for p in ["searched for", "buscó", "recherché", "gesucht nach", "ha cercato"]):
                    action = "Searched for " + link_text
                else:
                    action = "CLICK"
        else:
            action = cell_text
            
        # 3. Extract Page Title
        page_title = None
        if links:
            page_title = links[0].get_text(strip=True)
        if service == "Search" and "Searched for " in action:
            page_title = action.replace("Searched for ", "")
        if not page_title:
            page_title = action
            
        # 4. Extract Timestamp
        chunks = list(content_cell.stripped_strings)
        if caption:
            caption_strings = list(caption.stripped_strings)
            chunks = [c for c in chunks if c not in caption_strings]
            
        timestamp = None
        for chunk in reversed(chunks):
            # Google timestamps usually contain year and time (HH:MM)
            if re.search(r'\d{4}', chunk) and re.search(r'\d{1,2}:\d{2}', chunk):
                timestamp = clean_and_parse_localized_date(chunk)
                if timestamp:
                    break
                    
        if not timestamp:
            timestamp = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
            
        entries.append({
            'Service': service,
            'Action': action,
            'Timestamp': timestamp,
            'Links': url,
            'Page_Title': page_title
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
