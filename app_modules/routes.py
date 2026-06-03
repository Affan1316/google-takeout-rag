import io
import json
import pandas as pd
from datetime import datetime
from typing import List, Any, Optional
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import text

# Import from parse_takeout and parse_chrome_history at root level
from parse_takeout import parse_takeout_html
from parse_chrome_history import list_chrome_profiles, parse_chrome_history

# Package-relative imports
from .state import DBState, EmbeddingState, TAXONOMY
from .parser import (
    process_search_data,
    detect_service_type,
    enrich_youtube_data,
    store_youtube_history,
    store_search_history
)
from db_config import set_db_credentials, validate_connection
from .pipeline import run_async_indexing_pipeline
from .agent import init_db_and_agent

CSV_PROCESSOR_AVAILABLE = True

app = FastAPI(title="Hybrid RAG Agent API with CSV Processing")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==========================================
# PYDANTIC SCHEMAS
# ==========================================
class ChatRequest(BaseModel):
    query: str

class DBMessageSchema(BaseModel):
    text: str
    isUser: bool
    timestamp: str
    steps: Optional[List[Any]] = None

class DBSessionSchema(BaseModel):
    id: str
    title: str
    lastActive: str
    messages: List[DBMessageSchema]

class DBConnectRequest(BaseModel):
    db_project_ref: str
    db_password: str
    db_host: str = "aws-1-ap-northeast-1.pooler.supabase.com"
    db_port: str = "6543"
    llm_api_key: str

class ApplyDriftRequest(BaseModel):
    categories: List[str]

# ==========================================
# API ROUTE ENDPOINTS
# ==========================================

@app.post("/connect-db")
async def connect_db(request: DBConnectRequest):
    """Connect to Supabase and initialize the LangGraph Agent."""
    try:
        print(f"📥 Received connect-db request: project_ref='{request.db_project_ref}', host='{request.db_host}', port='{request.db_port}'")
        init_db_and_agent(
            request.db_project_ref,
            request.db_password,
            request.db_host,
            request.db_port,
            request.llm_api_key
        )
        return {"status": "success", "message": "Connected to database and initialized agent."}
    except Exception as e:
        print(f"❌ Failed to connect: {e}")
        raise HTTPException(status_code=400, detail=f"Failed to connect: {str(e)}")

@app.post("/disconnect-db")
async def disconnect_db():
    """Disconnect from Supabase, clear DBState, and clear session cache."""
    try:
        print("🔌 Received disconnect-db request. Clearing database state...")
        DBState.engine = None
        DBState.agent_executor = None
        DBState.project_ref = None
        DBState.password = None
        DBState.host = None
        DBState.port = None
        DBState.llm_api_key = None
        
        from db_config import clear_session_cache
        clear_session_cache()
        
        return {"status": "success", "message": "Successfully disconnected and cleared database state."}
    except Exception as e:
        print(f"❌ Failed to disconnect: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to disconnect: {str(e)}")

@app.post("/chat")
async def chat_with_agent(request: ChatRequest):
    """Main chat endpoint for RAG queries."""
    if not DBState.agent_executor:
        raise HTTPException(status_code=400, detail="Database not connected. Please upload a CSV with credentials first to initialize the agent.")

    try:
        # Pass the user's query into the LangGraph Agent
        result = DBState.agent_executor.invoke({"messages": [("user", request.query)]})
        
        # Extract the final AI text response
        final_answer = result["messages"][-1].content
        
        # Extract agent execution trace steps
        steps = []
        messages = result.get("messages", [])
        i = 0
        while i < len(messages):
            msg = messages[i]
            if msg.type == "ai" and getattr(msg, "tool_calls", None):
                thought = msg.content or ""
                actions = []
                for tc in msg.tool_calls:
                    actions.append({
                        "name": tc.get("name"),
                        "args": tc.get("args")
                    })
                
                observations = []
                i += 1
                while i < len(messages) and messages[i].type == "tool":
                    observations.append(messages[i].content)
                    i += 1
                
                steps.append({
                    "thought": thought,
                    "actions": actions,
                    "observations": observations
                })
                continue
            i += 1
            
        return {
            "response": final_answer,
            "steps": steps
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/chat-sessions")
async def get_chat_sessions():
    """Get all chat sessions and their messages stored in Supabase, ordered by last_active descending."""
    if not DBState.engine:
        raise HTTPException(status_code=400, detail="Database not connected.")
    try:
        sessions = []
        with DBState.engine.connect() as conn:
            db_sessions = conn.execute(text(
                "SELECT id, title, last_active FROM chat_sessions ORDER BY last_active DESC"
            )).fetchall()
            
            for s in db_sessions:
                s_id, title, last_active = s
                db_messages = conn.execute(text(
                    "SELECT text, is_user, timestamp, steps FROM chat_messages WHERE session_id = :sid ORDER BY id ASC"
                ), {"sid": s_id}).fetchall()
                
                messages = []
                for m in db_messages:
                    m_text, is_user, timestamp, steps = m
                    messages.append({
                        "text": m_text,
                        "isUser": is_user,
                        "timestamp": timestamp.isoformat() if timestamp else datetime.utcnow().isoformat(),
                        "steps": steps
                    })
                
                sessions.append({
                    "id": s_id,
                    "title": title,
                    "lastActive": last_active.isoformat() if last_active else datetime.utcnow().isoformat(),
                    "messages": messages
                })
        return sessions
    except Exception as e:
        print(f"❌ Error fetching chat sessions: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/chat-sessions")
async def save_chat_session(session: DBSessionSchema):
    """Save or update a single chat session and its associated messages in Supabase."""
    if not DBState.engine:
        raise HTTPException(status_code=400, detail="Database not connected.")
    try:
        try:
            last_active_dt = datetime.fromisoformat(session.lastActive.replace('Z', '+00:00'))
        except Exception:
            last_active_dt = datetime.utcnow()
            
        with DBState.engine.connect() as conn:
            with conn.begin():
                conn.execute(text("""
                    INSERT INTO chat_sessions (id, title, last_active)
                    VALUES (:id, :title, :last_active)
                    ON CONFLICT (id) DO UPDATE 
                    SET title = EXCLUDED.title, last_active = EXCLUDED.last_active
                """), {
                    "id": session.id,
                    "title": session.title,
                    "last_active": last_active_dt
                })
                
                conn.execute(text(
                    "DELETE FROM chat_messages WHERE session_id = :sid"
                ), {"sid": session.id})
                
                if session.messages:
                    insert_data = []
                    for m in session.messages:
                        try:
                            m_timestamp_dt = datetime.fromisoformat(m.timestamp.replace('Z', '+00:00'))
                        except Exception:
                            m_timestamp_dt = datetime.utcnow()
                            
                        insert_data.append({
                            "sid": session.id,
                            "text": m.text,
                            "is_user": m.isUser,
                            "timestamp": m_timestamp_dt,
                            "steps": json.dumps(m.steps) if m.steps is not None else None
                        })
                    
                    conn.execute(text("""
                        INSERT INTO chat_messages (session_id, text, is_user, timestamp, steps)
                        VALUES (:sid, :text, :is_user, :timestamp, CAST(:steps AS jsonb))
                    """), insert_data)
                    
        return {"status": "success", "message": f"Session '{session.id}' saved successfully."}
    except Exception as e:
        print(f"❌ Error saving chat session: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/chat-sessions/{session_id}")
async def delete_chat_session(session_id: str):
    """Delete a chat session (and cascade delete its messages) from Supabase."""
    if not DBState.engine:
        raise HTTPException(status_code=400, detail="Database not connected.")
    try:
        with DBState.engine.connect() as conn:
            with conn.begin():
                conn.execute(text(
                    "DELETE FROM chat_sessions WHERE id = :sid"
                ), {"sid": session_id})
        return {"status": "success", "message": f"Session '{session_id}' deleted successfully."}
    except Exception as e:
        print(f"❌ Error deleting chat session: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/upload-and-process-csv")
async def upload_and_process_csv(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    api_key: str = Form(default="")
):
    """Upload and process CSV or HTML files (YouTube or Search history)."""
    if not CSV_PROCESSOR_AVAILABLE:
        raise HTTPException(status_code=503, detail="CSV processor not available.")
    
    if not DBState.engine:
        raise HTTPException(status_code=400, detail="Database not connected. Please connect to Supabase first.")

    try:
        filename_lower = file.filename.lower()
        if not (filename_lower.endswith('.csv') or filename_lower.endswith('.html') or filename_lower.endswith('.htm')):
            raise HTTPException(status_code=400, detail="Only CSV or Google Takeout HTML files allowed")
        
        contents = await file.read()
        
        if filename_lower.endswith('.html') or filename_lower.endswith('.htm'):
            print(f"📥 Received HTML file: {file.filename}. Converting to DataFrame...")
            try:
                decoded_contents = contents.decode('utf-8')
            except UnicodeDecodeError:
                decoded_contents = contents.decode('latin-1')
            df = parse_takeout_html(decoded_contents)
            print(f"Parsed HTML into DataFrame with {len(df)} rows.")
        else:
            df = pd.read_csv(io.StringIO(contents.decode('utf-8')))
            print(f"📥 Received CSV: {file.filename} ({len(df)} rows)")
        
        required_columns = {'Service', 'Action', 'Timestamp', 'Links'}
        if not required_columns.issubset(df.columns):
            raise HTTPException(
                status_code=400, 
                detail=f"Uploaded data must contain columns: {required_columns}. Found: {set(df.columns)}"
            )
        
        service_type = detect_service_type(df)
        print(f"🔍 Detected service type: {service_type}")
        
        if service_type == 'youtube':
            if not api_key:
                raise HTTPException(status_code=400, detail="YouTube API key is required for YouTube data processing")
            
            print("▶️ Processing YouTube data...")
            result_df, quota_exceeded = enrich_youtube_data(df, api_key)
            rows_stored = store_youtube_history(result_df)
            
            background_tasks.add_task(run_async_indexing_pipeline, DBState.engine)
            
            status = "warning" if quota_exceeded else "success"
            msg = (
                f"⚠️ YouTube API Quota Exceeded! Partially processed and saved {rows_stored} records. "
                "The database is indexing vectors in the background for the saved records. Please try again tomorrow."
                if quota_exceeded else
                f"✅ Processed {len(df)} YouTube records. Stored {rows_stored} to database. Indexing vectors and classifying interests in the background..."
            )
            
            return {
                "status": status,
                "service_type": "youtube",
                "rows_processed": len(df),
                "rows_stored": rows_stored,
                "indexing": True,
                "message": msg,
                "quota_exceeded": quota_exceeded,
                "columns_added": [
                    "video_id", "Video_Title", "Video_Description",
                    "Channel_Title", "Category_ID", "Category_Name",
                    "View_Count", "Like_Count"
                ]
            }
        
        else:  # search
            print("▶️ Processing Search data...")
            result_df = process_search_data(df)
            rows_stored = store_search_history(result_df)
            
            background_tasks.add_task(run_async_indexing_pipeline, DBState.engine)
            
            return {
                "status": "success",
                "service_type": "search",
                "rows_processed": len(df),
                "rows_stored": rows_stored,
                "indexing": True,
                "message": f"✅ Processed {len(df)} Search records. Stored {rows_stored} to database. Indexing vectors and classifying interests in the background...",
                "columns_added": ["Actual_Website"]
            }
    
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error processing file: {e}")
        raise HTTPException(status_code=500, detail=f"Error processing file: {str(e)}")

@app.get("/chrome-profiles")
async def get_chrome_profiles():
    """Auto-discovers and returns available Chrome profiles on the local machine."""
    try:
        profiles = list_chrome_profiles()
        return {"profiles": profiles}
    except Exception as e:
        print(f"❌ Failed to fetch Chrome profiles: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list Chrome profiles: {str(e)}")

@app.post("/ingest-chrome-local")
async def ingest_chrome_local(
    background_tasks: BackgroundTasks,
    profile: str = Form(default="Default"),
    days: int = Form(default=None)
):
    """Automatically parses local Chrome history and directly ingests it."""
    if not DBState.engine:
        raise HTTPException(status_code=400, detail="Database not connected. Please connect to Supabase first.")
        
    try:
        import os
        print(f"📥 Automatically parsing local Chrome history for profile: {profile}...")
        
        yt_path, search_path = parse_chrome_history(
            profile=profile,
            days=days,
            output_dir="./temp"
        )
        
        search_rows_stored = 0
        rows_processed = 0
        
        if search_path and os.path.exists(search_path):
            print(f"📤 Storing Search/Browsing history in database from {search_path}...")
            search_df = pd.read_csv(search_path)
            if not search_df.empty:
                rows_processed = len(search_df)
                search_rows_stored = store_search_history(search_df)
        
        background_tasks.add_task(run_async_indexing_pipeline, DBState.engine)
        
        return {
            "status": "success",
            "message": f"Successfully parsed and ingested Chrome history for profile '{profile}'!",
            "rows_processed": rows_processed,
            "rows_stored": search_rows_stored,
            "service_type": "search",
            "indexing": True
        }
        
    except Exception as e:
        print(f"❌ Automated Chrome Ingestion failed: {e}")
        raise HTTPException(status_code=500, detail=f"Automated ingestion failed: {str(e)}")

@app.post("/process-csv/")
async def process_csv(
    file: UploadFile = File(..., description="CSV file to process"),
    api_key: str = Form(default="", description="YouTube API Key (required for YouTube data)"),
    db_project_ref: str = Form(default="", description="Supabase Project Ref (for storing embeddings)"),
    db_password: str = Form(default="", description="Supabase Password"),
    db_host: str = Form(default="aws-1-ap-northeast-1.pooler.supabase.com", description="Supabase Host"),
    db_port: str = Form(default="6543", description="Supabase Port")
):
    """Backward-compatible endpoint returning processed CSV data directly."""
    try:
        if db_project_ref:
            print(f"🔐 Validating Supabase credentials...")
            success, message = validate_connection(db_project_ref, db_password, db_host, db_port)
            if not success:
                raise HTTPException(status_code=400, detail=f"Supabase connection failed: {message}")
            print(message)
            set_db_credentials(db_project_ref, db_password, db_host, db_port)
        
        contents = await file.read()
        df = pd.read_csv(io.StringIO(contents.decode('utf-8')))
        
        required_columns = {'Service', 'Action', 'Timestamp', 'Links'}
        if not required_columns.issubset(df.columns):
            raise HTTPException(
                status_code=400, 
                detail=f"CSV must contain columns: {required_columns}. Found: {set(df.columns)}"
            )
        
        service_type = detect_service_type(df)
        
        if service_type == 'youtube':
            print("Routing to YouTube enrichment...")
            result_df, quota_exceeded = enrich_youtube_data(df, api_key)
            output_filename = "youtube_metadata_supervised.csv"
            headers = {
                "Content-Disposition": f"attachment; filename={output_filename}",
                "X-YouTube-Quota-Exceeded": "true" if quota_exceeded else "false"
            }
        else:
            print("Routing to Search data processor...")
            result_df = process_search_data(df)
            output_filename = "parsed_Search_with_Websites.csv"
            headers = {
                "Content-Disposition": f"attachment; filename={output_filename}"
            }
        
        output = io.BytesIO()
        result_df.to_csv(output, index=False)
        output.seek(0)
        
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers=headers
        )
    
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error processing CSV: {e}")
        raise HTTPException(status_code=500, detail=f"Error processing file: {str(e)}")

@app.get("/")
def read_root():
    """Health check endpoint"""
    return {
        "status": "FastAPI Server is running",
        "features": [
            "Hybrid RAG Agent ready",
            "CSV processing enabled" if CSV_PROCESSOR_AVAILABLE else "CSV processing disabled"
        ],
        "endpoints": {
            "POST /chat": "Chat with RAG agent about your history",
            "POST /upload-and-process-csv": "Upload and process CSV files",
            "POST /process-csv/": "Process CSV file and return processed version directly (backward-compatible)",
            "GET /": "This health check"
        }
    }

@app.get("/status")
def get_status():
    """Get detailed API status"""
    return {
        "api_version": "1.2",
        "csv_processor_available": CSV_PROCESSOR_AVAILABLE,
        "database_connected": DBState.engine is not None,
        "embeddings_loaded": True,
        "llm_available": DBState.llm_api_key is not None,
        "is_indexing": DBState.is_indexing,
        "indexing_message": DBState.indexing_message,
        "features": {
            "chat_with_agent": True,
            "csv_processing": CSV_PROCESSOR_AVAILABLE,
            "semantic_search": True,
            "sql_tools": True
        }
    }

@app.get("/drift-analysis")
async def get_drift_analysis():
    """Scans for low-confidence logs and suggests new categories."""
    if not DBState.engine:
        raise HTTPException(status_code=400, detail="Database not connected.")
    if not DBState.llm_api_key:
        raise HTTPException(status_code=400, detail="LLM API key not configured.")

    YT_THRESHOLD = 0.55
    SEARCH_THRESHOLD = 0.45

    try:
        with DBState.engine.connect() as conn:
            print("🔍 Scanning for logs below confidence thresholds...")
            unknown_logs_query = text("""
                WITH unclassified AS (
                    SELECT 
                        lc.id AS map_id, 
                        yh.video_title AS text, 
                        lc.confidence_score, 
                        'youtube' as source,
                        yh.id as raw_log_id
                    FROM log_classifications lc
                    JOIN youtube_history yh ON lc.youtube_log_id = yh.id
                    WHERE lc.youtube_log_id IS NOT NULL 
                      AND lc.confidence_score < :yt_thresh 
                      AND yh.drift_attempts < 2
                    
                    UNION ALL
                    
                    SELECT 
                        lc.id AS map_id, 
                        sh.actual_website AS text, 
                        lc.confidence_score, 
                        'search' as source,
                        sh.id as raw_log_id
                    FROM log_classifications lc
                    JOIN search_history sh ON lc.search_log_id = sh.id
                    WHERE lc.search_log_id IS NOT NULL 
                      AND lc.confidence_score < :search_thresh 
                      AND sh.drift_attempts < 2
                )
                SELECT * FROM unclassified ORDER BY confidence_score ASC LIMIT 50
            """)
            
            unknown_rows = conn.execute(unknown_logs_query, {"yt_thresh": YT_THRESHOLD, "search_thresh": SEARCH_THRESHOLD}).fetchall()
            
            if not unknown_rows:
                return {
                    "drift_found": False,
                    "suggested_categories": [],
                    "message": "✅ No taxonomy drift found! Your current interests cover your activity well."
                }
            
            # Cluster using LLM
            llm = ChatOpenAI(
                api_key=DBState.llm_api_key,
                base_url="https://api.deepseek.com",
                model="deepseek-chat",
                temperature=0.3
            )
            
            log_texts = [r[1] for r in unknown_rows if r[1]]
            
            from langchain_core.messages import SystemMessage
            prompt = f"""
            You are a highly precise taxonomy analyst maintaining a user interest taxonomy.
            The following digital activity logs did not match any of the user's existing interests.
            Your task is to analyze these logs and suggest 1 to 3 new broad category names representing genuine, intentional human learning or hobby interests (e.g., 'Home Repair', 'Time Management', 'Rust Programming').
            
            CRITICAL SAFETY RULES FOR NOISE ELIMINATION:
            1. Identify and skip any clusters dominated by ad-tracking pixels, redirects, system pings, web analytics, generic page loads, login pages, cookie walls, or accidental misclicks.
            2. If the logs are dominated by system noise, ads, or redirects, categorize them as "Noise" or "System/Ad Noise".
            3. Do NOT suggest categories for random ad URLs, tracking domains, or background network pings. Only suggest categories that a human would intentionally want to track as a personal topic of interest.
            
            Return ONLY a valid JSON list of strings representing the suggested categories (excluding any that are classified as "Noise" or "System/Ad Noise"). If everything is noise, return an empty list `[]`.
            Do not include markdown blocks, explanations, or any other characters.
            Example return: ["Home Repair", "Cybersecurity"]
            
            Logs to analyze:
            {json.dumps(log_texts[:30])}
            """
            
            response = llm.invoke([SystemMessage(content=prompt)])
            
            try:
                new_categories = json.loads(response.content.replace('```json', '').replace('```', '').strip())
                if not isinstance(new_categories, list):
                    new_categories = []
                new_categories = [
                    c.strip() for c in new_categories 
                    if c and isinstance(c, str) and not any(w in c.lower() for w in ["noise", "ad ", "ads ", "redirect", "system", "cookie", "pixel", "misclick", "analytics", "tracking"])
                ]
            except Exception as e:
                print(f"❌ Failed to parse LLM response: {e}. Raw content: {response.content}")
                raise HTTPException(status_code=500, detail=f"LLM did not return valid JSON: {response.content}")
                
            return {
                "drift_found": True,
                "suggested_categories": new_categories,
                "drifted_logs_sample": [
                    {"text": r[1], "source": r[3], "confidence": r[2]} for r in unknown_rows[:5]
                ],
                "message": f"Found {len(unknown_rows)} low-confidence logs. Suggested categories to add: {new_categories}"
            }
            
    except Exception as e:
        print(f"❌ Error running drift analysis: {e}")
        raise HTTPException(status_code=500, detail=f"Drift analysis failed: {str(e)}")

@app.post("/apply-drift")
async def apply_drift(request: ApplyDriftRequest, background_tasks: BackgroundTasks):
    """Applies suggested categories and resets low-confidence logs for re-classification."""
    if not DBState.engine:
        raise HTTPException(status_code=400, detail="Database not connected.")
    
    if not request.categories:
        raise HTTPException(status_code=400, detail="No categories provided to apply.")

    YT_THRESHOLD = 0.55
    SEARCH_THRESHOLD = 0.45

    try:
        embeddings_model = EmbeddingState.get_model()
        with DBState.engine.connect() as conn:
            print(f"Adding new categories: {request.categories}")
            for cat in request.categories:
                exists = conn.execute(
                    text("SELECT 1 FROM interest_categories WHERE LOWER(category_name) = LOWER(:name)"),
                    {"name": cat}
                ).scalar()
                if exists:
                    continue
                    
                vec = embeddings_model.embed_query(cat)
                
                # Find closest parent category using pgvector similarity
                parent_id = None
                try:
                    closest_parent = conn.execute(
                        text("""
                            SELECT id, category_name, 1 - (embedding <=> :vec::vector) AS similarity
                            FROM interest_categories
                            WHERE parent_id IS NULL
                            ORDER BY embedding <=> :vec::vector
                            LIMIT 1
                        """),
                        {"vec": str(vec)}
                    ).fetchone()
                    
                    if closest_parent:
                        p_id, p_name, sim = closest_parent
                        if sim >= 0.50:
                            parent_id = p_id
                            print(f"Mapped '{cat}' to parent '{p_name}' (similarity: {sim:.3f}) in route")
                except Exception as pe:
                    print(f"Error finding closest parent for {cat} in route: {pe}")

                conn.execute(
                    text("""
                        INSERT INTO interest_categories (category_name, embedding, is_global, parent_id)
                        VALUES (:name, :vec, false, :parent_id)
                    """),
                    {"name": cat, "vec": str(vec), "parent_id": parent_id}
                )
            
            print("Wiping low-confidence classifications so they can be re-categorized...")
            unknown_logs_query = text("""
                WITH unclassified AS (
                    SELECT 
                        lc.id AS map_id,
                        yh.id AS raw_log_id,
                        'youtube' AS source
                    FROM log_classifications lc
                    JOIN youtube_history yh ON lc.youtube_log_id = yh.id
                    WHERE lc.youtube_log_id IS NOT NULL 
                      AND lc.confidence_score < :yt_thresh
                      AND yh.drift_attempts < 2
                    
                    UNION ALL
                    
                    SELECT 
                        lc.id AS map_id,
                        sh.id AS raw_log_id,
                        'search' AS source
                    FROM log_classifications lc
                    JOIN search_history sh ON lc.search_log_id = sh.id
                    WHERE lc.search_log_id IS NOT NULL 
                      AND lc.confidence_score < :search_thresh
                      AND sh.drift_attempts < 2
                )
                SELECT map_id, raw_log_id, source FROM unclassified
            """)
            unknown_rows = conn.execute(unknown_logs_query, {"yt_thresh": YT_THRESHOLD, "search_thresh": SEARCH_THRESHOLD}).fetchall()
            map_ids = [r[0] for r in unknown_rows]
            
            yt_log_ids = [r[1] for r in unknown_rows if r[2] == 'youtube' and r[1] is not None]
            search_log_ids = [r[1] for r in unknown_rows if r[2] == 'search' and r[1] is not None]

            if yt_log_ids:
                if len(yt_log_ids) == 1:
                    conn.execute(text("UPDATE youtube_history SET drift_attempts = drift_attempts + 1 WHERE id = :id"), {"id": yt_log_ids[0]})
                else:
                    conn.execute(text("UPDATE youtube_history SET drift_attempts = drift_attempts + 1 WHERE id IN :ids"), {"ids": tuple(yt_log_ids)})

            if search_log_ids:
                if len(search_log_ids) == 1:
                    conn.execute(text("UPDATE search_history SET drift_attempts = drift_attempts + 1 WHERE id = :id"), {"id": search_log_ids[0]})
                else:
                    conn.execute(text("UPDATE search_history SET drift_attempts = drift_attempts + 1 WHERE id IN :ids"), {"ids": tuple(search_log_ids)})
            
            if map_ids:
                if len(map_ids) == 1:
                    conn.execute(text("DELETE FROM log_classifications WHERE id = :id"), {"id": map_ids[0]})
                else:
                    conn.execute(text("DELETE FROM log_classifications WHERE id IN :ids"), {"ids": tuple(map_ids)})
            
            conn.commit()

        background_tasks.add_task(run_async_indexing_pipeline, DBState.engine)
        
        return {
            "status": "success",
            "message": f"Successfully added categories: {request.categories}. Wiped low-confidence classifications and triggered background re-classification task."
        }
            
    except Exception as e:
        print(f"❌ Error applying drift: {e}")
        raise HTTPException(status_code=500, detail=f"Apply drift failed: {str(e)}")
