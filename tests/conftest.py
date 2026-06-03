import pytest
from fastapi.testclient import TestClient
from app_modules.routes import app
from app_modules.state import DBState

@pytest.fixture
def client():
    # Reset DBState before each test to maintain isolation
    DBState.engine = None
    DBState.agent_executor = None
    DBState.project_ref = None
    DBState.password = None
    DBState.host = None
    DBState.port = None
    DBState.llm_api_key = None
    
    with TestClient(app) as c:
        yield c
