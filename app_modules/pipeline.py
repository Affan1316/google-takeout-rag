import time
import pandas as pd
from sqlalchemy import text
from .state import DBState, EmbeddingState
from .parser import clean_url_to_semantic_text

def generate_embeddings_task(db_engine):
    """Generates BGE-small embeddings for newly uploaded records lacking them."""
    print("🧠 Starting Embedding Generation Task...")
    embeddings_model = EmbeddingState.get_model()
    
    # YouTube embedding
    print("🔍 Fetching YouTube history without embeddings...")
    with db_engine.connect() as conn:
        df = pd.read_sql(
            "SELECT id, video_title, channel_title FROM youtube_history WHERE embedding IS NULL AND video_title IS NOT NULL", 
            conn
        )
        
        if df.empty:
            print("✅ All YouTube videos are already embedded!")
        else:
            print(f"🧠 Generating vectors for {len(df)} YouTube videos...")
            texts = (df['video_title'] + " (Channel: " + df['channel_title'].fillna("Unknown") + ")").tolist()
            vectors = embeddings_model.embed_documents(texts)
            
            print("💾 Saving YouTube vectors to Supabase...")
            for i, vec in zip(df['id'], vectors):
                conn.execute(
                    text("UPDATE youtube_history SET embedding = :vec WHERE id = :id"),
                    {"vec": str(vec), "id": i}
                )
            conn.commit()
            print("✅ YouTube embedding complete!")
            
    # Search embedding
    print("🔍 Fetching Search history without embeddings...")
    with db_engine.connect() as conn:
        df = pd.read_sql(
            "SELECT id, action, page_title, links FROM search_history WHERE embedding IS NULL AND (action IS NOT NULL OR page_title IS NOT NULL OR links IS NOT NULL)", 
            conn
        )
        
        if df.empty:
            print("✅ All Search queries are already embedded!")
        else:
            print(f"🧠 Generating vectors for {len(df)} Search queries...")
            texts = []
            for _, row in df.iterrows():
                page_title = str(row.get('page_title', '')).strip() if pd.notna(row.get('page_title')) else ""
                action = str(row.get('action', '')).strip() if pd.notna(row.get('action')) else ""
                links = str(row.get('links', '')).strip() if pd.notna(row.get('links')) else ""
                
                if page_title:
                    texts.append(page_title)
                elif action and not action.startswith("CLICK") and not action.startswith("SEARCH"):
                    texts.append(action.replace("Searched for ", ""))
                elif links:
                    texts.append(clean_url_to_semantic_text(links))
                else:
                    texts.append(action or "Web Visit")
                    
            vectors = embeddings_model.embed_documents(texts)
            
            print("💾 Saving Search vectors to Supabase...")
            for i, vec in zip(df['id'], vectors):
                conn.execute(
                    text("UPDATE search_history SET embedding = :vec WHERE id = :id"),
                    {"vec": str(vec), "id": i}
                )
            conn.commit()
            print("✅ Search embedding complete!")

def classify_historical_logs_task(db_engine):
    """Classifies unclassified records using nearest interest_categories embedding natively in-database via pgvector."""
    print("🧠 Starting In-Database Vector Log Classification...")
    batch_size = 5000
    
    try:
        # Check if taxonomy exists first
        with db_engine.connect() as conn:
            cat_count = conn.execute(
                text("SELECT COUNT(*) FROM interest_categories WHERE embedding IS NOT NULL")
            ).scalar()
            if cat_count == 0:
                print("⚠️ No taxonomy categories with embeddings found. Seeding taxonomy categories first is recommended.")
                return
        
        # Using AUTOCOMMIT to avoid long-running transaction locks and API timeouts
        with db_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            
            # --- YOUTUBE CLASSIFICATION ---
            print("\n▶️ Starting YouTube History Classification...")
            iteration = 1
            while True:
                # We use LEFT JOIN which is vastly faster than NOT IN for massive tables
                # We also ensure we only grab rows that actually have embeddings.
                sql = """
                    INSERT INTO log_classifications (youtube_log_id, category_id, confidence_score)
                    SELECT 
                        y.id AS youtube_log_id,
                        ic.id AS category_id,
                        (1 - (y.embedding <=> ic.embedding)) AS confidence_score
                    FROM (
                        SELECT yh.id, yh.embedding 
                        FROM youtube_history yh
                        LEFT JOIN log_classifications lc ON lc.youtube_log_id = yh.id
                        WHERE lc.id IS NULL AND yh.embedding IS NOT NULL
                        LIMIT :batch_size
                    ) y
                    CROSS JOIN LATERAL (
                        SELECT id, embedding
                        FROM interest_categories
                        ORDER BY embedding <=> y.embedding
                        LIMIT 1
                    ) ic;
                """
                
                result = conn.execute(text(sql), {"batch_size": batch_size})
                rows_inserted = result.rowcount
                
                print(f"  Iteration {iteration}: Classified {rows_inserted} YouTube logs.")
                
                if rows_inserted == 0:
                    break
                iteration += 1

            # --- SEARCH CLASSIFICATION ---
            print("\n▶️ Starting Search History Classification...")
            iteration = 1
            while True:
                sql = """
                    INSERT INTO log_classifications (search_log_id, category_id, confidence_score)
                    SELECT 
                        s.id AS search_log_id,
                        ic.id AS category_id,
                        (1 - (s.embedding <=> ic.embedding)) AS confidence_score
                    FROM (
                        SELECT sh.id, sh.embedding 
                        FROM search_history sh
                        LEFT JOIN log_classifications lc ON lc.search_log_id = sh.id
                        WHERE lc.id IS NULL AND sh.embedding IS NOT NULL
                        LIMIT :batch_size
                    ) s
                    CROSS JOIN LATERAL (
                        SELECT id, embedding
                        FROM interest_categories
                        ORDER BY embedding <=> s.embedding
                        LIMIT 1
                    ) ic;
                """
                
                result = conn.execute(text(sql), {"batch_size": batch_size})
                rows_inserted = result.rowcount
                
                print(f"  Iteration {iteration}: Classified {rows_inserted} Search logs.")
                
                if rows_inserted == 0:
                    break
                iteration += 1

        print("🎉 In-Database Log Classification completed successfully!")
        
    except Exception as e:
        print(f"❌ Classification failed: {e}")

def run_async_indexing_pipeline(db_engine):
    """Background task runner for embeddings and classifications with transient error recovery"""
    if DBState.is_indexing:
        print("⚠️ Indexing pipeline is already running. Skipping trigger.")
        return
        
    DBState.is_indexing = True
    max_retries = 3
    
    for attempt in range(max_retries):
        try:
            DBState.indexing_message = "Generating BGE-small vector embeddings..."
            generate_embeddings_task(db_engine)
            
            DBState.indexing_message = "Performing nearest-category classification..."
            classify_historical_logs_task(db_engine)
            
            DBState.indexing_message = "Ready"
            print("🎉 Background RAG Ingestion Pipeline completed successfully!")
            DBState.is_indexing = False
            return
        except Exception as e:
            print(f"⚠️ Background RAG Ingestion Pipeline attempt {attempt + 1}/{max_retries} failed: {e}")
            if attempt < max_retries - 1:
                sleep_time = 5 * (attempt + 1)
                DBState.indexing_message = f"Retrying indexing in {sleep_time}s..."
                time.sleep(sleep_time)
            else:
                print("❌ Background RAG Ingestion Pipeline fully failed.")
                DBState.indexing_message = f"Failed: {str(e)}"
                
    DBState.is_indexing = False
