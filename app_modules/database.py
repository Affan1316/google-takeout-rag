import os
from sqlalchemy import text
from .state import TAXONOMY, EmbeddingState

def verify_and_initialize_db(db_engine):
    """
    Checks if required tables exist in Supabase.
    If not, automatically executes migrations and seeds taxonomy categories.
    Also ensures all specific columns (like page_title, embedding, and drift_attempts) exist.
    """
    # 1. Enable vector extension
    try:
        with db_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
    except Exception as e:
        print(f"⚠️ Warning enabling vector extension: {e}")

    # 2. search_history upgrades
    try:
        with db_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            conn.execute(text("ALTER TABLE search_history ADD COLUMN IF NOT EXISTS page_title TEXT;"))
            conn.execute(text("ALTER TABLE search_history ADD COLUMN IF NOT EXISTS embedding vector(384);"))
            conn.execute(text("ALTER TABLE search_history ADD COLUMN IF NOT EXISTS drift_attempts INTEGER DEFAULT 0;"))
    except Exception as e:
        print(f"⚠️ Warning upgrading search_history columns: {e}")

    # 3. youtube_history upgrades
    try:
        with db_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            conn.execute(text("ALTER TABLE youtube_history ADD COLUMN IF NOT EXISTS embedding vector(384);"))
            conn.execute(text("ALTER TABLE youtube_history ADD COLUMN IF NOT EXISTS drift_attempts INTEGER DEFAULT 0;"))
    except Exception as e:
        print(f"⚠️ Warning upgrading youtube_history columns: {e}")

    # 4. chat_sessions and chat_messages tables
    try:
        with db_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS chat_sessions (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    last_active TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
            """))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id SERIAL PRIMARY KEY,
                    session_id TEXT REFERENCES chat_sessions(id) ON DELETE CASCADE,
                    text TEXT NOT NULL,
                    is_user BOOLEAN NOT NULL,
                    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    steps JSONB
                );
            """))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_chat_msg_session ON chat_messages(session_id);"))
            
            # Enable Row Level Security (consistent with interest_categories & log_classifications)
            conn.execute(text("ALTER TABLE chat_sessions ENABLE ROW LEVEL SECURITY;"))
            conn.execute(text("ALTER TABLE chat_messages ENABLE ROW LEVEL SECURITY;"))
            
            print("✅ Chat history tables verified/created with RLS enabled!")
    except Exception as e:
        print(f"⚠️ Warning creating chat history tables: {e}")

    print("🔍 Verifying database tables...")
    tables_exist = False
    try:
        with db_engine.connect() as conn:
            conn.execute(text("SELECT 1 FROM interest_categories LIMIT 1"))
            conn.execute(text("SELECT 1 FROM log_classifications LIMIT 1"))
            tables_exist = True
            print("✅ Database tables verified!")
    except Exception:
        print("⚠️ Required tables missing. Initializing database schema...")
        tables_exist = False

    if not tables_exist:
        # 1. Create Core History Tables if they don't exist
        print("▶️ Creating raw history tables and enabling pgvector...")
        init_sql = """
        CREATE TABLE IF NOT EXISTS search_history (
            id SERIAL PRIMARY KEY,
            service TEXT,
            action TEXT,
            timestamp TIMESTAMP,
            links TEXT,
            actual_website TEXT
        );

        CREATE TABLE IF NOT EXISTS youtube_history (
            id SERIAL PRIMARY KEY,
            service TEXT,
            action TEXT,
            timestamp TIMESTAMP,
            links TEXT,
            video_id TEXT,
            video_title TEXT,
            video_description TEXT,
            channel_title TEXT,
            category_id BIGINT,
            category_name TEXT,
            view_count BIGINT,
            like_count BIGINT
        );

        CREATE INDEX IF NOT EXISTS idx_search_time ON search_history(timestamp);
        CREATE INDEX IF NOT EXISTS idx_youtube_time ON youtube_history(timestamp);

        CREATE EXTENSION IF NOT EXISTS vector;
        """
        try:
            with db_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
                for stmt in init_sql.split(";"):
                    if stmt.strip():
                        conn.execute(text(stmt))
                
                # Add vector columns if they don't exist
                try:
                    conn.execute(text("ALTER TABLE youtube_history ADD COLUMN embedding vector(384)"))
                except Exception as e:
                    if "already exists" not in str(e).lower():
                        print(f"Warning adding embedding to youtube_history: {e}")
                try:
                    conn.execute(text("ALTER TABLE search_history ADD COLUMN embedding vector(384)"))
                except Exception as e:
                    if "already exists" not in str(e).lower():
                        print(f"Warning adding embedding to search_history: {e}")
                # Add page_title column for Chrome history data
                try:
                    conn.execute(text("ALTER TABLE search_history ADD COLUMN page_title TEXT"))
                except Exception as e:
                    if "already exists" not in str(e).lower():
                        print(f"Warning adding page_title to search_history: {e}")
            print("✅ Raw tables and vector extension prepared.")
        except Exception as e:
            print(f"❌ Failed to prepare raw tables: {e}")

        # 2. Run Phase 1 Schema Migration (interest_categories, log_classifications)
        sql_file_path = 'phase1_schema_update.sql'
        if os.path.exists(sql_file_path):
            print(f"▶️ Loading schema from {sql_file_path}...")
            with open(sql_file_path, 'r', encoding='utf-8') as f:
                sql_script = f.read()
            
            with db_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
                statements = [s.strip() for s in sql_script.split(';') if s.strip()]
                for i, statement in enumerate(statements):
                    if not statement or (statement.startswith('--') and len(statement.split('\n')) == 1):
                        continue
                    try:
                        conn.execute(text(statement))
                    except Exception as stmt_e:
                        error_msg = str(stmt_e).lower()
                        if "already exists" in error_msg or "multiple primary keys" in error_msg:
                            continue
                        else:
                            print(f"⚠️ Statement {i+1} warning: {stmt_e}")
            print("✅ Phase 1 schema migration complete.")
        else:
            print(f"❌ Could not find {sql_file_path} for migration!")

        # 3. Seed taxonomy categories using global embeddings model
        print("▶️ Seeding taxonomy categories into database...")
        try:
            embeddings_model = EmbeddingState.get_model()
            with db_engine.connect() as conn:
                result = conn.execute(text("SELECT COUNT(*) FROM interest_categories")).scalar()
                if result == 0:
                    for parent_cat, sub_cats in TAXONOMY.items():
                        print(f"  └─ Seeding parent: {parent_cat}")
                        parent_vector = embeddings_model.embed_query(parent_cat)
                        
                        res = conn.execute(
                            text("""
                                INSERT INTO interest_categories (category_name, embedding, is_global, parent_id)
                                VALUES (:name, :vec, true, NULL)
                                RETURNING id
                            """),
                            {"name": parent_cat, "vec": str(parent_vector)}
                        )
                        parent_id = res.scalar()
                        
                        for sub_cat in sub_cats:
                            sub_vector = embeddings_model.embed_query(sub_cat)
                            conn.execute(
                                text("""
                                    INSERT INTO interest_categories (category_name, embedding, is_global, parent_id)
                                    VALUES (:name, :vec, true, :parent)
                                """),
                                {"name": sub_cat, "vec": str(sub_vector), "parent": parent_id}
                            )
                    conn.commit()
                    print("✅ Taxonomy seeding complete!")
                else:
                    print(f"⚠️ Found {result} existing categories, skipping seed.")
        except Exception as e:
            print(f"❌ Error seeding taxonomy: {e}")
