#!/usr/bin/env python
"""
Test Data Generator

Generates sample YouTube and Search CSV files for testing the API
"""

import pandas as pd
from datetime import datetime, timedelta
import random

def generate_test_youtube_csv():
    """Generate sample YouTube CSV data"""
    
    youtube_video_ids = [
        'dQw4w9WgXcQ',  # Rick Roll
        'jNQXAC9IVRw',  # Me at the zoo (first YouTube video)
        '9bZkp7q19f0',  # Evolution of Dance
        'Bvl3bU-Jl7E',  # Pen Pineapple Apple Pen
        'kJQP7kiw9Fk',  # Gangnam Style
        'V1bFr2SWP1I',  # Despacito
        'fMyt2j7D1rM',  # Despacito (Remix)
        'l28UKQe5QLo',  # No Woman No Cry
        'e-IWRmpefzE',  # Smack My Bitch Up
        '9EMw3qNiGBE',  # One Direction
    ]
    
    base_time = datetime(2024, 1, 1, 10, 0, 0)
    
    data = {
        'Service': ['YouTube'] * len(youtube_video_ids),
        'Action': ['WATCH'] * len(youtube_video_ids),
        'Timestamp': [(base_time + timedelta(hours=i)).isoformat() + 'Z' for i in range(len(youtube_video_ids))],
        'Links': [f'https://www.youtube.com/watch?v={vid}' for vid in youtube_video_ids]
    }
    
    df = pd.DataFrame(data)
    df.to_csv('test_youtube_sample.csv', index=False)
    print(f"[Success] Generated: test_youtube_sample.csv ({len(df)} rows)")
    print(f"   Sample rows:")
    print(df.head(3).to_string(index=False))
    return df

def generate_test_search_csv():
    """Generate sample Search CSV data"""
    
    websites = [
        'https://www.google.com/url?q=https%3A%2F%2Fgithub.com',
        'https://www.google.com/url?q=https%3A%2F%2Fstackoverflow.com',
        'https://www.google.com/url?q=https%3A%2F%2Fpython.org',
        'https://www.google.com/url?q=https%3A%2F%2Fdocs.python.org',
        'https://www.google.com/url?q=https%3A%2F%2Fmedium.com',
        'https://www.google.com/url?q=https%3A%2F%2Ftowardsdatascience.com',
        'https://www.google.com/url?q=https%3A%2F%2Fkaggle.com',
        'https://www.google.com/url?q=https%3A%2F%2Fpandas.pydata.org',
        'https://www.google.com/url?q=https%3A%2F%2Fnumpy.org',
        'https://developer.android.com',
    ]
    
    base_time = datetime(2024, 1, 1, 10, 0, 0)
    
    data = {
        'Service': ['Search'] * len(websites),
        'Action': ['CLICK'] * len(websites),
        'Timestamp': [(base_time + timedelta(hours=i)).isoformat() + 'Z' for i in range(len(websites))],
        'Links': websites
    }
    
    df = pd.DataFrame(data)
    df.to_csv('test_search_sample.csv', index=False)
    print(f"\n[Success] Generated: test_search_sample.csv ({len(df)} rows)")
    print(f"   Sample rows:")
    print(df.head(3).to_string(index=False))
    return df

def main():
    print("\n" + "=" * 70)
    print("  Test Data Generator - CSV Processor")
    print("=" * 70 + "\n")
    
    # Generate YouTube sample
    print("Creating YouTube test data...")
    youtube_df = generate_test_youtube_csv()
    
    # Generate Search sample
    print("\nCreating Search test data...")
    search_df = generate_test_search_csv()
    
    print("\n" + "=" * 70)
    print("[Success] Test files created successfully!")
    print("\nYou can now test the API with these files:")
    print("  - test_youtube_sample.csv (requires YouTube API key)")
    print("  - test_search_sample.csv (no API key needed)")
    print("\nExample usage:")
    print("  python client.py test_youtube_sample.csv YOUR_API_KEY")
    print("  python client.py test_search_sample.csv")
    print("=" * 70 + "\n")

if __name__ == "__main__":
    main()
