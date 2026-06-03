import pytest
from app_modules.parser import clean_url_to_semantic_text, extract_video_id, normalize_timestamp_str
from app_modules.state import DBState

# ==========================================
# 1. UNIT TESTS FOR PARSING HELPERS
# ==========================================

def test_clean_url_to_semantic_text():
    # Test typical URL parsing
    url = "https://www.google.com/search?q=rust+lang"
    assert clean_url_to_semantic_text(url) == "google.com / search"
    
    url_slugs = "https://github.com/rust-lang/rust/pulls"
    assert clean_url_to_semantic_text(url_slugs) == "github.com / rust lang / rust / pulls"
    
    # Test file extension stripping and digit filtering
    url_digits = "https://example.com/user/12345/profile.html"
    assert clean_url_to_semantic_text(url_digits) == "example.com / user / profile"
    
    # Test blank URL
    assert clean_url_to_semantic_text("") == ""
    assert clean_url_to_semantic_text(None) == ""

def test_extract_video_id():
    # Test typical watch link
    assert extract_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    # Test YouTube shorts link
    assert extract_video_id("https://youtube.com/shorts/dQw4w9WgXcQ?feature=share") == "dQw4w9WgXcQ"
    # Test short URL
    assert extract_video_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    # Test embed URL
    assert extract_video_id("https://www.youtube.com/embed/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    # Test invalid links
    assert extract_video_id("https://example.com") is None
    assert extract_video_id(None) is None

def test_normalize_timestamp_str():
    # Standard timestamp format
    assert normalize_timestamp_str("2024-01-01 12:00:00") == "2024-01-01 12:00:00"
    # ISO 8601 with Z
    assert normalize_timestamp_str("2024-01-01T12:00:00Z") == "2024-01-01 12:00:00"
    # Invalid date strings should return themselves
    assert normalize_timestamp_str("Not-A-Date") == "Not-A-Date"
    # Empty string should return empty string
    assert normalize_timestamp_str("") == ""

# ==========================================
# 2. UNIT TESTS FOR API ROUTE PROTECTION (DISCONNECTED STATE)
# ==========================================

def test_health_check_endpoint(client):
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "FastAPI Server is running" in data["status"]
    assert "endpoints" in data

def test_status_endpoint_disconnected(client):
    response = client.get("/status")
    assert response.status_code == 200
    data = response.json()
    assert data["database_connected"] is False
    assert data["llm_available"] is False
    assert data["is_indexing"] is False

def test_chat_disconnected(client):
    response = client.post("/chat", json={"query": "test"})
    assert response.status_code == 400
    assert "Database not connected" in response.json()["detail"]

def test_chat_sessions_disconnected(client):
    response = client.get("/chat-sessions")
    assert response.status_code == 400
    assert "Database not connected" in response.json()["detail"]

def test_upload_disconnected(client):
    # Dummy file upload
    files = {"file": ("test.csv", b"Service,Action,Timestamp,Links\nSearch,Search,2024-01-01,https://example.com")}
    response = client.post("/upload-and-process-csv", files=files, data={"api_key": "dummy"})
    assert response.status_code == 400
    assert "Database not connected" in response.json()["detail"]

def test_chrome_ingestion_disconnected(client):
    response = client.post("/ingest-chrome-local", data={"profile": "Default"})
    assert response.status_code == 400
    assert "Database not connected" in response.json()["detail"]

def test_drift_analysis_disconnected(client):
    response = client.get("/drift-analysis")
    assert response.status_code == 400
    assert "Database not connected" in response.json()["detail"]
