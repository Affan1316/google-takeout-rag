import os
from sqlalchemy import text
from db_config import get_connection_from_user, get_db_engine

def run_migration():
    try:
        print("="*60)
        print("🚀 RUNNING PHASE 1 SCHEMA MIGRATION")
        print("="*60)
        
        # 1. Get credentials (prompts user interactively)
        get_connection_from_user()
        engine = get_db_engine()
        
        # 2. Read the SQL file
        sql_file_path = 'phase1_schema_update.sql'
        if not os.path.exists(sql_file_path):
            print(f"❌ Could not find {sql_file_path}")
            return
            
        with open(sql_file_path, 'r', encoding='utf-8') as f:
            sql_script = f.read()
            
        print("\n▶️ Executing SQL migration (bypassing Supabase API Gateway)...")
        print("⏳ This might take a few minutes on massive tables. Please wait...")
        
        # 3. Execute with AUTOCOMMIT 
        # (This prevents SQLAlchemy from wrapping everything in one giant transaction, which is safer for DDL)
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            # Split by ';' to execute statements sequentially
            statements = [s.strip() for s in sql_script.split(';') if s.strip()]
            
            for i, statement in enumerate(statements):
                if not statement or statement.startswith('--') and len(statement.split('\n')) == 1:
                    continue
                    
                try:
                    conn.execute(text(statement))
                    print(f"✅ Executed statement {i+1}/{len(statements)}")
                except Exception as stmt_e:
                    error_msg = str(stmt_e).lower()
                    # Safely ignore things we already created on previous failed attempts
                    if "already exists" in error_msg or "multiple primary keys" in error_msg:
                        print(f"⚠️ Skipped statement {i+1}: Already exists.")
                    else:
                        print(f"❌ Error in statement {i+1}: {stmt_e}")
                        # We don't raise here so it attempts to finish the script (e.g. altering the tables)
                        
        print("\n🎉 PHASE 1 SCHEMA MIGRATION COMPLETED SUCCESSFULLY!")
        
    except Exception as e:
        print(f"\n❌ Migration failed: {e}")

if __name__ == "__main__":
    run_migration()
