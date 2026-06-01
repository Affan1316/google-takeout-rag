import urllib.parse
from sqlalchemy import create_engine, text
from typing import Optional, Dict, Any, Tuple

# ==========================================
# SESSION-LEVEL CREDENTIAL CACHING
# ==========================================
_session_cache: Dict[str, Any] = {
    'engine': None,
    'credentials': {}
}

def set_db_credentials(
    project_ref: str,
    password: str,
    host: str = "aws-1-ap-northeast-1.pooler.supabase.com",
    port: str = "6543"
):
    """
    Store credentials in session cache and return engine.
    Credentials are cached for the duration of the session.
    """
    _session_cache['credentials'] = {
        'project_ref': project_ref,
        'password': password,
        'host': host,
        'port': port
    }
    return get_db_engine()

def get_db_engine():
    """Get cached database engine, or create new one if credentials set."""
    if _session_cache['engine'] is not None:
        return _session_cache['engine']
    
    creds = _session_cache.get('credentials', {})
    if not creds or not all(k in creds for k in ['project_ref', 'password', 'host', 'port']):
        raise ValueError("Database credentials not set. Call set_db_credentials() first.")
    
    project_ref = creds['project_ref']
    password = creds['password']
    host = creds['host']
    port = creds['port']
    
    safe_password = urllib.parse.quote_plus(password)
    DB_URI = f"postgresql://postgres.{project_ref}:{safe_password}@{host}:{port}/postgres"
    
    _session_cache['engine'] = create_engine(
        DB_URI,
        pool_pre_ping=True,
        pool_recycle=300,
        pool_size=10,
        max_overflow=20
    )
    return _session_cache['engine']

def validate_connection(project_ref: str, password: str, host: str = "aws-1-ap-northeast-1.pooler.supabase.com", port: str = "6543") -> Tuple[bool, str]:
    """
    Test connection to Supabase without caching.
    Returns (success: bool, message: str)
    """
    try:
        safe_password = urllib.parse.quote_plus(password)
        DB_URI = f"postgresql://postgres.{project_ref}:{safe_password}@{host}:{port}/postgres"
        test_engine = create_engine(DB_URI)
        
        with test_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        
        return True, "✅ Connection successful!"
    except Exception as e:
        return False, f"❌ Connection failed: {str(e)}"

def get_connection_from_user(use_defaults: bool = False) -> Dict[str, str]:
    """
    Interactively prompt user for Supabase credentials.
    Returns credentials dict.
    """
    print("\n" + "="*60)
    print("  SUPABASE DATABASE CREDENTIALS")
    print("="*60)
    
    if use_defaults and _session_cache['credentials']:
        print("\n✅ Using cached credentials from this session")
        return _session_cache['credentials']
    
    project_ref = input("Enter Supabase Project Ref (e.g., lqxvoarityebqongdiru): ").strip()
    if not project_ref:
        raise ValueError("Project Ref is required")
    
    password = input("Enter Supabase Password: ").strip()
    if not password:
        raise ValueError("Password is required")
    
    host = input("Enter Supabase Host [default: aws-1-ap-northeast-1.pooler.supabase.com]: ").strip()
    if not host:
        host = "aws-1-ap-northeast-1.pooler.supabase.com"
    
    port = input("Enter Supabase Port [default: 6543]: ").strip()
    if not port:
        port = "6543"
    
    # Validate connection
    print("\n🔍 Validating connection...")
    success, message = validate_connection(project_ref, password, host, port)
    print(message)
    
    if not success:
        raise ValueError("Invalid credentials")
    
    # Cache and return
    set_db_credentials(project_ref, password, host, port)
    return _session_cache['credentials']

def clear_session_cache():
    """Clear cached credentials and engine (for testing or manual refresh)."""
    _session_cache['engine'] = None
    _session_cache['credentials'] = {}
    print("✅ Session cache cleared")
