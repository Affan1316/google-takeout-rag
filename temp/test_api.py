#!/usr/bin/env python
"""
Comprehensive Test Suite for CSV Processor API

Tests both YouTube and Search data processing through the API
"""

import requests
import pandas as pd
import sys
import time
from pathlib import Path

BASE_URL = "http://localhost:8000"
TIMEOUT = 30

# ANSI color codes
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'

def print_section(title):
    """Print a formatted section header"""
    print(f"\n{BLUE}{'='*70}{RESET}")
    print(f"{BLUE}{title.center(70)}{RESET}")
    print(f"{BLUE}{'='*70}{RESET}\n")

def test_api_health():
    """Test if API is running"""
    print("🔍 Testing API Health...")
    try:
        response = requests.get(f"{BASE_URL}/health/", timeout=5)
        if response.status_code == 200:
            print(f"{GREEN}✅ API is running and healthy!{RESET}")
            data = response.json()
            print(f"   Status: {data.get('status')}")
            print(f"   Message: {data.get('message')}")
            return True
        else:
            print(f"{RED}❌ API returned status code: {response.status_code}{RESET}")
            return False
    except requests.exceptions.ConnectionError:
        print(f"{RED}❌ Could not connect to API at {BASE_URL}{RESET}")
        print(f"   Please make sure the API is running: python main.py")
        return False
    except Exception as e:
        print(f"{RED}❌ Error: {e}{RESET}")
        return False

def test_search_processing():
    """Test Search data processing"""
    print("📊 Testing Search Data Processing...")
    
    # Create test data
    search_data = {
        'Service': ['Search'] * 3,
        'Action': ['CLICK'] * 3,
        'Timestamp': [
            '2024-01-01T10:00:00Z',
            '2024-01-01T11:00:00Z',
            '2024-01-01T12:00:00Z'
        ],
        'Links': [
            'https://www.google.com/url?q=https%3A%2F%2Fgithub.com',
            'https://www.google.com/url?q=https%3A%2F%2Fstackoverflow.com',
            'https://www.google.com/url?q=https%3A%2F%2Fpython.org'
        ]
    }
    
    df = pd.DataFrame(search_data)
    csv_path = 'test_search_input.csv'
    df.to_csv(csv_path, index=False)
    
    print(f"   Created test file: {csv_path}")
    print(f"   Test data preview:")
    print(df.to_string(index=False))
    
    try:
        with open(csv_path, 'rb') as f:
            response = requests.post(
                f"{BASE_URL}/process-csv/",
                files={'file': f},
                timeout=TIMEOUT
            )
        
        if response.status_code == 200:
            # Save output
            output_path = 'test_search_output.csv'
            with open(output_path, 'wb') as f:
                f.write(response.content)
            
            # Verify output
            result_df = pd.read_csv(output_path)
            print(f"\n{GREEN}✅ Search processing successful!{RESET}")
            print(f"   Output file: {output_path}")
            print(f"   Rows: {len(result_df)}")
            print(f"   Columns: {list(result_df.columns)}")
            print(f"\n   Output preview:")
            print(result_df.to_string(index=False))
            
            # Check for Actual_Website column
            if 'Actual_Website' in result_df.columns:
                print(f"\n{GREEN}✅ Actual_Website column found!{RESET}")
                print(f"   Extracted websites:")
                for idx, website in enumerate(result_df['Actual_Website'], 1):
                    print(f"      {idx}. {website}")
            else:
                print(f"{YELLOW}⚠️ Actual_Website column not found{RESET}")
            
            return True
        else:
            error_detail = response.json().get('detail', response.text)
            print(f"{RED}❌ Error: {error_detail}{RESET}")
            return False
    
    except requests.exceptions.Timeout:
        print(f"{RED}❌ Request timeout{RESET}")
        return False
    except Exception as e:
        print(f"{RED}❌ Exception: {e}{RESET}")
        return False

def test_youtube_processing(api_key=None):
    """Test YouTube data processing"""
    print("📺 Testing YouTube Data Processing...")
    
    if not api_key:
        print(f"{YELLOW}⚠️ Skipping YouTube test - no API key provided{RESET}")
        print(f"   To test YouTube processing, run: python test_api.py YOUR_YOUTUBE_API_KEY")
        return None
    
    # Create test data with valid YouTube video IDs
    youtube_data = {
        'Service': ['YouTube'] * 2,
        'Action': ['WATCH'] * 2,
        'Timestamp': ['2024-01-01T10:00:00Z', '2024-01-01T11:00:00Z'],
        'Links': [
            'https://www.youtube.com/watch?v=dQw4w9WgXcQ',  # Rick Roll
            'https://www.youtube.com/watch?v=jNQXAC9IVRw'   # First YouTube video
        ]
    }
    
    df = pd.DataFrame(youtube_data)
    csv_path = 'test_youtube_input.csv'
    df.to_csv(csv_path, index=False)
    
    print(f"   Created test file: {csv_path}")
    print(f"   Using API key: {api_key[:8]}...")
    print(f"   Test data preview:")
    print(df.to_string(index=False))
    
    try:
        with open(csv_path, 'rb') as f:
            response = requests.post(
                f"{BASE_URL}/process-csv/",
                files={'file': f},
                data={'api_key': api_key},
                timeout=TIMEOUT
            )
        
        if response.status_code == 200:
            # Save output
            output_path = 'test_youtube_output.csv'
            with open(output_path, 'wb') as f:
                f.write(response.content)
            
            # Verify output
            result_df = pd.read_csv(output_path)
            print(f"\n{GREEN}✅ YouTube processing successful!{RESET}")
            print(f"   Output file: {output_path}")
            print(f"   Rows: {len(result_df)}")
            print(f"   Columns: {list(result_df.columns)}")
            print(f"\n   Output preview (first few columns):")
            print(result_df[['Links', 'video_id', 'Video_Title', 'Channel_Title']].to_string(index=False))
            
            # Check for expected columns
            expected_cols = ['video_id', 'Video_Title', 'Video_Description', 'Channel_Title', 
                           'Category_ID', 'Category_Name', 'View_Count', 'Like_Count']
            missing_cols = [col for col in expected_cols if col not in result_df.columns]
            
            if missing_cols:
                print(f"\n{YELLOW}⚠️ Missing columns: {missing_cols}{RESET}")
            else:
                print(f"\n{GREEN}✅ All expected columns found!{RESET}")
            
            return True
        else:
            error_detail = response.json().get('detail', response.text)
            print(f"{RED}❌ Error: {error_detail}{RESET}")
            return False
    
    except requests.exceptions.Timeout:
        print(f"{RED}❌ Request timeout{RESET}")
        return False
    except Exception as e:
        print(f"{RED}❌ Exception: {e}{RESET}")
        return False

def test_invalid_file():
    """Test error handling with invalid file"""
    print("⚠️ Testing Error Handling (Invalid File)...")
    
    # Create invalid CSV (missing Service column)
    invalid_data = {
        'Action': ['TEST'],
        'Timestamp': ['2024-01-01T10:00:00Z'],
        'Links': ['https://example.com']
    }
    
    df = pd.DataFrame(invalid_data)
    csv_path = 'test_invalid.csv'
    df.to_csv(csv_path, index=False)
    
    try:
        with open(csv_path, 'rb') as f:
            response = requests.post(
                f"{BASE_URL}/process-csv/",
                files={'file': f},
                timeout=TIMEOUT
            )
        
        if response.status_code == 400:
            error = response.json()
            print(f"{GREEN}✅ API correctly rejected invalid file!{RESET}")
            print(f"   Error: {error.get('detail')}")
            return True
        else:
            print(f"{RED}❌ Expected 400 error but got {response.status_code}{RESET}")
            return False
    
    except Exception as e:
        print(f"{RED}❌ Exception: {e}{RESET}")
        return False

def main():
    """Run all tests"""
    print_section("CSV Processor API - Test Suite")
    
    # Parse command line arguments
    api_key = sys.argv[1] if len(sys.argv) > 1 else None
    
    # Test API health
    if not test_api_health():
        print(f"\n{RED}Cannot continue. API is not running.{RESET}")
        return False
    
    print_section("Running Tests")
    
    results = {
        'health': True,
        'search': None,
        'youtube': None,
        'invalid': None
    }
    
    # Test Search processing
    results['search'] = test_search_processing()
    
    # Test YouTube processing
    results['youtube'] = test_youtube_processing(api_key)
    
    # Test error handling
    results['invalid'] = test_invalid_file()
    
    # Summary
    print_section("Test Summary")
    
    tests_run = sum(1 for v in results.values() if v is not None)
    tests_passed = sum(1 for v in results.values() if v is True)
    
    print(f"Tests Run: {tests_run}")
    print(f"Tests Passed: {tests_passed}")
    print(f"Tests Skipped: {sum(1 for v in results.values() if v is None)}")
    
    for test_name, result in results.items():
        if result is True:
            status = f"{GREEN}✅ PASSED{RESET}"
        elif result is False:
            status = f"{RED}❌ FAILED{RESET}"
        else:
            status = f"{YELLOW}⏭️  SKIPPED{RESET}"
        
        print(f"  {test_name.ljust(15)}: {status}")
    
    print_section("Output Files")
    
    output_files = [
        'test_search_input.csv',
        'test_search_output.csv',
        'test_youtube_input.csv',
        'test_youtube_output.csv',
        'test_invalid.csv'
    ]
    
    for file in output_files:
        if Path(file).exists():
            size = Path(file).stat().st_size
            print(f"  📄 {file} ({size} bytes)")
    
    print_section("Next Steps")
    
    if results['search'] is True:
        print(f"{GREEN}✅ Search processing is working!{RESET}")
    
    if results['youtube'] is True:
        print(f"{GREEN}✅ YouTube processing is working!{RESET}")
    elif results['youtube'] is None:
        print(f"{YELLOW}To test YouTube processing:{RESET}")
        print(f"  1. Get a YouTube API key from: https://console.cloud.google.com/")
        print(f"  2. Run: python test_api.py YOUR_YOUTUBE_API_KEY")
    
    print(f"\n{BLUE}API documentation:{RESET}")
    print(f"  Swagger UI: {BASE_URL}/docs")
    print(f"  ReDoc: {BASE_URL}/redoc")
    
    return all(v is True or v is None for v in results.values())

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
