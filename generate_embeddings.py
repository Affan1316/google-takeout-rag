import pandas as pd
from sqlalchemy import text
from langchain_huggingface import HuggingFaceEmbeddings
from db_config import get_db_engine, get_connection_from_user, set_db_credentials

# ==========================================
# 1. DATABASE CONNECTION (DYNAMIC)
# ==========================================
engine = None  # Will be initialized at runtime

# ==========================================
# 2. INITIALIZE BGE MODEL
# ==========================================
print("📥 Downloading/Loading BGE-Small model (~130MB)...")
# BGE performs best when embeddings are normalized (cosine similarity becomes dot product)
embeddings = HuggingFaceEmbeddings(
    model_name="BAAI/bge-small-en-v1.5",
    encode_kwargs={'normalize_embeddings': True} 
)

# ==========================================
# 3. EMBED YOUTUBE DATA
# ==========================================
def embed_youtube(db_engine):
    print("🔍 Fetching YouTube history without embeddings...")
    with db_engine.connect() as conn:
        # Fetch rows that don't have embeddings yet
        df = pd.read_sql(
            "SELECT id, video_title, channel_title FROM youtube_history WHERE embedding IS NULL AND video_title IS NOT NULL", 
            conn
        )
        
        if df.empty:
            print("✅ All YouTube videos are already embedded!")
            return

        print(f"🧠 Generating vectors for {len(df)} YouTube videos...")
        # Combine title and channel to give the AI maximum context
        texts = (df['video_title'] + " (Channel: " + df['channel_title'].fillna("Unknown") + ")").tolist()
        
        # We DO NOT use the instruction prefix here, because these are the "documents" being searched
        vectors = embeddings.embed_documents(texts)
        
        print("💾 Saving YouTube vectors to Supabase...")
        for i, vec in zip(df['id'], vectors):
            # Convert Python list to string format required by pgvector: "[0.1, 0.2, ...]"
            conn.execute(
                text("UPDATE youtube_history SET embedding = :vec WHERE id = :id"),
                {"vec": str(vec), "id": i}
            )
        conn.commit()
        print("✅ YouTube embedding complete!")

# ==========================================
# 4. EMBED SEARCH DATA
# ==========================================
def embed_search(db_engine):
    print("\n🔍 Fetching Search history without embeddings...")
    with db_engine.connect() as conn:
        df = pd.read_sql(
            "SELECT id, action FROM search_history WHERE embedding IS NULL AND action IS NOT NULL", 
            conn
        )
        
        if df.empty:
            print("✅ All Search queries are already embedded!")
            return

        print(f"🧠 Generating vectors for {len(df)} Search queries...")
        # Clean the "Searched for " prefix out of the action text to keep the embedding pure
        texts = df['action'].str.replace("Searched for ", "", regex=False).tolist()
        
        vectors = embeddings.embed_documents(texts)
        
        print("💾 Saving Search vectors to Supabase...")
        for i, vec in zip(df['id'], vectors):
            conn.execute(
                text("UPDATE search_history SET embedding = :vec WHERE id = :id"),
                {"vec": str(vec), "id": i}
            )
        conn.commit()
        print("✅ Search embedding complete!")

# ==========================================
# 5. EXECUTE
# ==========================================
if __name__ == "__main__":
    try:
        # Get credentials from user (cached per session)
        print("🚀 PHASE 3.5: INITIALIZE EMBEDDINGS WITH YOUR SUPABASE")
        get_connection_from_user(use_defaults=False)
        db_engine = get_db_engine()
        
        embed_youtube(db_engine)
        embed_search(db_engine)
        print("\n🚀 PHASE 3.5 COMPLETE: Your database is now semantically aware!")
        
    except ValueError as e:
        print(f"❌ Error: {e}")
        exit(1)
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        exit(1)