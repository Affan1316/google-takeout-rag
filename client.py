#!/usr/bin/env python
"""
Interactive CSV Processor Client

Simple command-line interface to interact with the CSV Processor API
"""

import requests
import os
import sys
from pathlib import Path

BASE_URL = "http://localhost:8000"

def get_supabase_credentials(use_cached=True):
    """Get Supabase credentials from user, with optional caching"""
    from db_config import _session_cache, validate_connection
    
    if use_cached and _session_cache.get('credentials'):
        print("\n✅ Using cached Supabase credentials from this session")
        return _session_cache['credentials']
    
    print("\n" + "="*60)
    print("  SUPABASE DATABASE CREDENTIALS (for storing embeddings)")
    print("="*60)
    
    project_ref = input("\nEnter Supabase Project Ref [optional - skip for no storage]: ").strip()
    
    if not project_ref:
        print("⚠️ No Supabase credentials provided - embeddings won't be stored")
        return None
    
    password = input("Enter Supabase Password: ").strip()
    host = input("Enter Supabase Host [default: aws-1-ap-northeast-1.pooler.supabase.com]: ").strip() or "aws-1-ap-northeast-1.pooler.supabase.com"
    port = input("Enter Supabase Port [default: 6543]: ").strip() or "6543"
    
    # Validate connection
    print("\n🔍 Validating Supabase connection...")
    success, message = validate_connection(project_ref, password, host, port)
    print(message)
    
    if not success:
        raise ValueError("Invalid Supabase credentials")
    
    credentials = {
        'project_ref': project_ref,
        'password': password,
        'host': host,
        'port': port
    }
    
    _session_cache['credentials'] = credentials
    return credentials

def print_header(text):
    """Print a formatted header"""
    print("\n" + "=" * 60)
    print(f"  {text}")
    print("=" * 60 + "\n")

def check_api_health():
    """Check if API is running"""
    try:
        response = requests.get(f"{BASE_URL}/health/", timeout=5)
        if response.status_code == 200:
            print("✅ API is running and healthy!")
            return True
        else:
            print(f"❌ API returned status code: {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print("❌ Could not connect to API at " + BASE_URL)
        print("   Make sure the API is running: python main.py")
        return False
    except Exception as e:
        print(f"❌ Error checking API health: {e}")
        return False

def process_file(file_path, api_key=None, db_credentials=None):
    """Process a CSV file through the API"""
    
    # Validate file exists
    if not os.path.exists(file_path):
        print(f"❌ File not found: {file_path}")
        return False
    
    # Check file extension
    if not file_path.lower().endswith('.csv'):
        print("❌ File must be a CSV file (.csv)")
        return False
    
    try:
        print(f"📤 Uploading file: {file_path}")
        
        with open(file_path, 'rb') as f:
            files = {'file': f}
            data = {}
            
            # Add API key if provided
            if api_key:
                data['api_key'] = api_key
                print(f"🔑 Using YouTube API key: {api_key[:8]}...")
            
            # Add Supabase credentials if provided
            if db_credentials:
                data['db_project_ref'] = db_credentials.get('project_ref', '')
                data['db_password'] = db_credentials.get('password', '')
                data['db_host'] = db_credentials.get('host', 'aws-1-ap-northeast-1.pooler.supabase.com')
                data['db_port'] = db_credentials.get('port', '6543')
                print(f"🗄️ Using Supabase project: {db_credentials.get('project_ref', '')[:8]}...")
            
            # Send request
            response = requests.post(
                f"{BASE_URL}/process-csv/",
                files=files,
                data=data,
                timeout=300  # 5 minute timeout for large files
            )
        
        # Handle response
        if response.status_code == 200:
            # Save output file
            output_name = response.headers.get('content-disposition', '')
            if 'filename=' in output_name:
                filename = output_name.split('filename=')[1].strip('"')
            else:
                filename = Path(file_path).stem + "_processed.csv"
            
            with open(filename, 'wb') as out_file:
                out_file.write(response.content)
            
            print(f"✅ Processing complete!")
            print(f"📥 Output saved to: {filename}")
            return True
        else:
            error_data = response.json()
            error_msg = error_data.get('detail', str(error_data))
            print(f"❌ Error: {error_msg}")
            return False
    
    except requests.exceptions.Timeout:
        print("❌ Request timeout. The file might be too large or the API is slow.")
        return False
    except requests.exceptions.ConnectionError:
        print("❌ Could not connect to API. Make sure it's running.")
        return False
    except Exception as e:
        print(f"❌ Error processing file: {e}")
        return False

def interactive_mode():
    """Interactive menu mode"""
    print_header("CSV Data Processor - Interactive Mode")
    
    # Check API health
    if not check_api_health():
        print("Please start the API server and try again.")
        return
    
    # Get Supabase credentials once per session
    db_credentials = None
    
    while True:
        print("\nOptions:")
        print("1. Process a CSV file")
        print("2. Check API status")
        print("3. Set/Update Supabase credentials")
        print("4. Exit")
        print()
        
        choice = input("Choose an option (1-4): ").strip()
        
        if choice == '1':
            file_path = input("\nEnter path to CSV file: ").strip()
            
            # Check if YouTube data
            try:
                import pandas as pd
                df = pd.read_csv(file_path)
                service = df.iloc[0]['Service'].lower()
                
                api_key = None
                if 'youtube' in service:
                    api_key = input("Enter YouTube API key: ").strip()
                    if not api_key:
                        print("⚠️  YouTube API key is required for YouTube data!")
                        continue
                
                # Get DB credentials if not already set
                if not db_credentials:
                    try:
                        db_credentials = get_supabase_credentials(use_cached=True)
                    except Exception as e:
                        print(f"⚠️ Supabase setup error: {e}")
                        db_credentials = None
                
                process_file(file_path, api_key, db_credentials)
            except pd.errors.ParserError:
                print("❌ Invalid CSV file format")
            except Exception as e:
                print(f"❌ Error reading file: {e}")
        
        elif choice == '2':
            check_api_health()
        
        elif choice == '3':
            try:
                db_credentials = get_supabase_credentials(use_cached=False)
                print("✅ Supabase credentials updated")
            except Exception as e:
                print(f"❌ Error: {e}")
                db_credentials = None
        
        elif choice == '4':
            print("\n👋 Goodbye!")
            break
        
        else:
            print("❌ Invalid choice. Please try again.")

def main():
    """Main entry point"""
    print_header("CSV Data Processor Client")
    
    # Check for command-line arguments
    if len(sys.argv) > 1:
        # Non-interactive mode
        file_path = sys.argv[1]
        api_key = sys.argv[2] if len(sys.argv) > 2 else None
        
        print(f"File: {file_path}")
        if api_key:
            print(f"API Key: {api_key[:8]}...")
        print()
        
        # Check API first
        if not check_api_health():
            sys.exit(1)
        
        # Process file
        success = process_file(file_path, api_key)
        sys.exit(0 if success else 1)
    
    else:
        # Interactive mode
        interactive_mode()

if __name__ == "__main__":
    main()
