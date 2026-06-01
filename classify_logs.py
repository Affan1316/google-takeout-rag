import os
from sqlalchemy import text
from db_config import get_connection_from_user, get_db_engine

def classify_historical_logs():
    print("="*60)
    print("🧠 RUNNING PHASE 2: IN-DATABASE VECTOR CLASSIFICATION")
    print("="*60)
    
    # 1. Connect
    get_connection_from_user()
    engine = get_db_engine()
    
    batch_size = 5000
    
    try:
        # Using AUTOCOMMIT to avoid long-running transaction locks and API timeouts
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            
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

        print("\n🎉 PHASE 2 CLASSIFICATION COMPLETED SUCCESSFULLY!")
        
    except Exception as e:
        print(f"\n❌ Classification failed: {e}")

if __name__ == "__main__":
    classify_historical_logs()
