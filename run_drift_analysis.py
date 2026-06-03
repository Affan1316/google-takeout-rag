import os
import json
from sqlalchemy import text
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage
from langchain_huggingface import HuggingFaceEmbeddings
from db_config import get_connection_from_user, get_db_engine

# Dual Confidence Thresholds (Cosine Similarity)
# 1.0 is a perfect match, 0.0 is completely orthogonal.
YT_THRESHOLD = 0.55       # YouTube has rich text, expect higher similarity
SEARCH_THRESHOLD = 0.45   # Search is sparse text, tolerate lower similarity

def run_drift_analysis():
    print("="*60)
    print("🔍 RUNNING PHASE 4: DYNAMIC DRIFT & ANOMALY ENGINE")
    print("="*60)
    
    get_connection_from_user()
    engine = get_db_engine()
    
    api_key = input("\nEnter DeepSeek LLM API Key (for category generation): ").strip()
    if not api_key:
        print("❌ API Key required.")
        return
        
    llm = ChatOpenAI(
        api_key=api_key,
        base_url="https://api.deepseek.com",
        model="deepseek-chat",
        temperature=0.3
    )
    
    print("\nLoading BAAI/bge-small-en-v1.5 embedding model...")
    embeddings_model = HuggingFaceEmbeddings(
        model_name="BAAI/bge-small-en-v1.5",
        encode_kwargs={'normalize_embeddings': True}
    )
    
    with engine.connect() as conn:
        # 1. Fetch "Unknown/Drift" Logs (Below confidence threshold)
        print("\nScanning for logs below confidence thresholds...")
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
            print("✅ No drift found! Your taxonomy perfectly covers all your digital history.")
            return
            
        print(f"⚠️ Found {len(unknown_rows)} highly distant logs (Potential Drift or Anomalies).")
        print("Sample of unknown logs:")
        for r in unknown_rows[:5]:
            print(f" - [{r[3]}] {r[1]} (Score: {r[2]:.2f})")
            
        # 4.2 Anomaly Exclusion Step (Simulated for CLI)
        print("\n[Anomaly Exclusion] Are these legitimate new interests, or account-sharing noise (e.g. someone else watching cartoons)?")
        action = input("Type 'generate' to create new categories, or 'discard' to mark as noise: ").strip().lower()
        
        if action == 'discard':
            print("🗑️ Discarding logs as noise. (In a full app, this would set an is_anomaly flag).")
            # For now, we will just delete the classifications so they don't pollute the stats
            # or leave them as is with a low score. To actually hide them, we delete them from raw tables.
            return
            
        # 2. Ask LLM to generate new categories
        print("\n🧠 Asking LLM to analyze drift and cluster into new categories...")
        log_texts = [r[1] for r in unknown_rows if r[1]]
        
        prompt = f"""
        You are an AI maintaining a cyberpsychology taxonomy.
        The following digital activity logs did not match any of the user's existing interests.
        Please cluster these activities and suggest 1 to 3 new broad category names that capture this new behavior.
        Return ONLY a valid JSON list of strings. No markdown, no explanation.
        Example: ["Home Repair", "Local Politics"]
        
        Logs to classify:
        {json.dumps(log_texts[:30])}
        """
        
        response = llm.invoke([SystemMessage(content=prompt)])
        
        try:
            new_categories = json.loads(response.content.replace('```json', '').replace('```', '').strip())
        except:
            print("❌ Failed to parse LLM response. Raw output:")
            print(response.content)
            return
            
        if not new_categories or not isinstance(new_categories, list):
            print("❌ LLM did not suggest any valid categories.")
            return
            
        print(f"✅ LLM Suggested New Categories: {new_categories}")
        
        # 3. Embed and Insert New Categories
        print("\nEmbedding and inserting new categories...")
        for cat in new_categories:
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
                    # Threshold of 0.50 for parent assignment
                    if sim >= 0.50:
                        parent_id = p_id
                        print(f"  └─ Mapped '{cat}' to parent '{p_name}' (similarity: {sim:.3f})")
                    else:
                        print(f"  └─ '{cat}' is orthogonal (max similarity to {p_name} is {sim:.3f}), inserting at root.")
            except Exception as pe:
                print(f"  ⚠️ Error finding closest parent for {cat}: {pe}")
            
            # Insert as a personal category (is_global = false)
            conn.execute(
                text("""
                    INSERT INTO interest_categories (category_name, embedding, is_global, parent_id)
                    VALUES (:name, :vec, false, :parent_id)
                """),
                {"name": cat, "vec": str(vec), "parent_id": parent_id}
            )
            print(f"  └─ Inserted: {cat}")
            
        # 4. Wipe classifications for the unknown rows so Phase 2 can re-run
        print("\nWiping low-confidence classifications so they can be re-categorized...")
        
        # Increment drift_attempts for the raw records first so they aren't swept indefinitely
        yt_log_ids = [r[4] for r in unknown_rows if r[3] == 'youtube' and r[4] is not None]
        search_log_ids = [r[4] for r in unknown_rows if r[3] == 'search' and r[4] is not None]

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

        map_ids = tuple([r[0] for r in unknown_rows])
        if len(map_ids) == 1:
            conn.execute(text("DELETE FROM log_classifications WHERE id = :id"), {"id": map_ids[0]})
        else:
            conn.execute(text("DELETE FROM log_classifications WHERE id IN :ids"), {"ids": map_ids})
            
        conn.commit()
        print("\n🎉 PHASE 4 COMPLETE!")
        print("You can now re-run `python classify_logs.py` to instantly map the unknown logs to your newly discovered interests!")

if __name__ == "__main__":
    run_drift_analysis()
