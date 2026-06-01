# CSV Data Processor API

A FastAPI application that intelligently routes CSV files through appropriate processors based on their service type (YouTube or Search).

## Features

✅ **Automatic Service Detection**: Detects whether a CSV contains YouTube or Search data based on the first row  
✅ **YouTube Enrichment**: Enriches YouTube data with video metadata (title, description, channel, views, likes, etc.)  
✅ **Search Processing**: Extracts actual website domains from Google redirect URLs  
✅ **Dynamic API Key**: Accepts YouTube API key as input (no hardcoding needed)  
✅ **Rate Limiting Handling**: Implements exponential backoff for API rate limits  
✅ **Interactive API Docs**: Built-in Swagger UI and ReDoc documentation  

## Installation

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Verify Installation

```bash
python -c "import fastapi; import pandas; import requests; print('All dependencies installed ✅')"
```

## Running the API

### Start the Server

```bash
python main.py
```

The API will start on `http://localhost:8000`

### Access the Documentation

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **Health Check**: http://localhost:8000/health/

## Input File Format

Both YouTube and Search CSV files must have these columns:

| Column | Type | Example |
|--------|------|---------|
| Service | String | "YouTube" or "Search" |
| Action | String | "WATCH", "CLICK", etc. |
| Timestamp | String (ISO 8601) | "2024-01-01T10:00:00Z" |
| Links | String (URL) | "https://www.youtube.com/watch?v=..." |

## API Endpoints

### POST /process-csv/

Process a CSV file based on its service type.

**Parameters:**
- `file` (FormData): The CSV file to process
- `api_key` (FormData, optional): YouTube API key (required for YouTube data)

**Example Usage with curl:**

```bash
# For YouTube data
curl -X POST "http://localhost:8000/process-csv/" \
  -F "file=@parsed_YouTube.csv" \
  -F "api_key=YOUR_YOUTUBE_API_KEY"

# For Search data (no API key needed)
curl -X POST "http://localhost:8000/process-csv/" \
  -F "file=@parsed_Search.csv"
```

**Example Usage with Python:**

```python
import requests

# YouTube processing
with open('parsed_YouTube.csv', 'rb') as f:
    response = requests.post(
        'http://localhost:8000/process-csv/',
        files={'file': f},
        data={'api_key': 'YOUR_YOUTUBE_API_KEY'}
    )
    with open('output.csv', 'wb') as out:
        out.write(response.content)

# Search processing
with open('parsed_Search.csv', 'rb') as f:
    response = requests.post(
        'http://localhost:8000/process-csv/',
        files={'file': f}
    )
    with open('output.csv', 'wb') as out:
        out.write(response.content)
```

### GET /health/

Health check endpoint.

```bash
curl http://localhost:8000/health/
```

Response:
```json
{"status": "OK", "message": "CSV Processor API is running"}
```

## Output Files

### YouTube Processing Output
- **Filename**: `youtube_metadata_supervised.csv`
- **New Columns Added**:
  - `video_id`: Extracted video ID
  - `Video_Title`: Video title
  - `Video_Description`: First 200 characters of description
  - `Channel_Title`: Channel name
  - `Category_ID`: YouTube category ID
  - `Category_Name`: Human-readable category name
  - `View_Count`: Number of views
  - `Like_Count`: Number of likes

### Search Processing Output
- **Filename**: `parsed_Search_with_Websites.csv`
- **New Columns Added**:
  - `Actual_Website`: Extracted domain name (handles Google redirects)

## Getting a YouTube API Key

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project
3. Enable the YouTube Data API v3
4. Create an API key from the credentials page
5. Use this key when submitting YouTube data to the API

## Example Test

Run the included example script:

```bash
python example_usage.py
```

This will:
1. Create sample YouTube and Search CSV files
2. Send them to the API for processing
3. Save the enriched results to output files

**Note**: Update `YOUR_YOUTUBE_API_KEY` in `example_usage.py` with your actual API key before running.

## Error Handling

### Common Errors

| Error | Cause | Solution |
|-------|-------|----------|
| "API key is required" | No YouTube API key provided for YouTube data | Add `api_key` parameter |
| "CSV must contain columns" | Missing required columns | Ensure file has Service, Action, Timestamp, Links |
| "Unknown service type" | Service column doesn't contain 'YouTube' or 'Search' | Check the Service column value |
| "Could not connect to API" | Server not running | Start the server with `python main.py` |

### Rate Limiting

The YouTube API has quota limits. The application automatically handles rate limiting with exponential backoff:
- 1st retry: Wait 2 seconds
- 2nd retry: Wait 3 seconds  
- 3rd retry: Wait 5 seconds

## Performance Notes

- **Processing Speed**: Depends on number of unique videos/links and YouTube API quota
- **Batch Size**: Processes 50 video IDs per API request (YouTube limit)
- **Delay**: 0.5 second delay between batches to avoid quota exhaustion
- **Timeout**: 10 second timeout for each API request

## Troubleshooting

### API Not Starting?

```bash
# Check if port 8000 is already in use
netstat -ano | findstr :8000  # Windows
lsof -i :8000  # Mac/Linux

# Try a different port
uvicorn main:app --host 0.0.0.0 --port 8001
```

### Import Errors?

```bash
# Reinstall all dependencies
pip install --upgrade -r requirements.txt
```

### YouTube API Errors?

- Verify API key is valid and enabled for YouTube Data API v3
- Check your quota: https://console.cloud.google.com/apis/dashboard
- Ensure video IDs are valid (11 characters: a-z, A-Z, 0-9, _, -)

## Architecture

```
main.py
├── FastAPI Application
├── YouTube Enrichment Module
│   ├── extract_video_id()
│   ├── fetch_dynamic_categories()
│   ├── fetch_with_retry()
│   └── enrich_youtube_data()
├── Search Processing Module
│   ├── get_actual_website()
│   └── process_search_data()
├── Detection & Routing
│   └── detect_service_type()
└── API Endpoints
    ├── POST /process-csv/
    ├── GET /health/
    └── GET /
```

## License

This project is provided as-is for personal use.

## Support

For issues or questions, check:
1. The error message and logs
2. API documentation: http://localhost:8000/docs
3. YouTube API documentation: https://developers.google.com/youtube/v3
