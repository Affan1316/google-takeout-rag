import requests
import pandas as pd

# Example usage of the CSV Processor API

# ============ EXAMPLE 1: PROCESS YOUTUBE DATA ============
print("=" * 60)
print("Example 1: Processing YouTube Data")
print("=" * 60)

# Prepare YouTube CSV file
youtube_data = {
    'Service': ['YouTube'] * 3,
    'Action': ['WATCH'] * 3,
    'Timestamp': ['2024-01-01T10:00:00Z', '2024-01-01T11:00:00Z', '2024-01-01T12:00:00Z'],
    'Links': [
        'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
        'https://www.youtube.com/watch?v=jNQXAC9IVRw',
        'https://www.youtube.com/watch?v=9bZkp7q19f0'
    ]
}
youtube_df = pd.DataFrame(youtube_data)
youtube_df.to_csv('test_youtube.csv', index=False)

# Send to API with YouTube API Key
with open('test_youtube.csv', 'rb') as f:
    files = {'file': f}
    data = {'api_key': 'YOUR_YOUTUBE_API_KEY'}  # Replace with your actual API key
    
    try:
        response = requests.post(
            'http://localhost:8000/process-csv/',
            files=files,
            data=data
        )
        
        if response.status_code == 200:
            with open('youtube_output.csv', 'wb') as out_file:
                out_file.write(response.content)
            print("✅ YouTube data processed successfully!")
            print(f"Output saved to: youtube_output.csv")
        else:
            print(f"❌ Error: {response.status_code}")
            print(response.json())
    except requests.exceptions.ConnectionError:
        print("❌ Could not connect to API. Make sure it's running on http://localhost:8000")

# ============ EXAMPLE 2: PROCESS SEARCH DATA ============
print("\n" + "=" * 60)
print("Example 2: Processing Search Data")
print("=" * 60)

# Prepare Search CSV file
search_data = {
    'Service': ['Search'] * 3,
    'Action': ['CLICK'] * 3,
    'Timestamp': ['2024-01-01T10:00:00Z', '2024-01-01T11:00:00Z', '2024-01-01T12:00:00Z'],
    'Links': [
        'https://www.google.com/url?q=https%3A%2F%2Fgithub.com',
        'https://www.google.com/url?q=https%3A%2F%2Fstackoverflow.com',
        'https://developer.android.com'
    ]
}
search_df = pd.DataFrame(search_data)
search_df.to_csv('test_search.csv', index=False)

# Send to API (no API key needed for Search data)
with open('test_search.csv', 'rb') as f:
    files = {'file': f}
    
    try:
        response = requests.post(
            'http://localhost:8000/process-csv/',
            files=files,
            data={}  # No API key needed for Search
        )
        
        if response.status_code == 200:
            with open('search_output.csv', 'wb') as out_file:
                out_file.write(response.content)
            print("✅ Search data processed successfully!")
            print(f"Output saved to: search_output.csv")
        else:
            print(f"❌ Error: {response.status_code}")
            print(response.json())
    except requests.exceptions.ConnectionError:
        print("❌ Could not connect to API. Make sure it's running on http://localhost:8000")

print("\n" + "=" * 60)
print("Examples completed!")
print("=" * 60)
