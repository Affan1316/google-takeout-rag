#!/usr/bin/env python
"""
Supabase RAG Database Reset Utility

Wipes all records from the history logs, classifications, and taxonomy categories
so you can perform a clean re-ingestion of your browsing data.
"""

import sys
from sqlalchemy import text

# Import the cached DB config helper from the workspace
try:
    from db_config import get_connection_from_user, get_db_engine
except ImportError:
    print("❌ ERROR: db_config.py not found in the current directory.")
    print("Please run this script from the root workspace folder: d:\\GOOGLE_TAKEOUT_RAG")
    sys.exit(1)


def main():
    print("\n" + "=" * 60)
    print("      SUPABASE DATABASE RESET & WIPE UTILITY 🧹")
    print("=" * 60)
    print("\n[WARNING] This script will permanently delete all records from:")
    print("  • log_classifications (All categorized logs)")
    print("  • search_history      (All browser & search logs)")
    print("  • youtube_history     (All YouTube watch logs)")
    print("  • interest_categories (Taxonomy interests - will be auto-reseeded on next run)")
    print("\nThis action is irreversible.")
    
    confirm = input("\n⚠️ Are you absolutely sure you want to proceed? Type 'WIPE' to confirm: ").strip()
    if confirm != "WIPE":
        print("❌ Reset cancelled. No changes were made to the database.")
        sys.exit(0)
        
    try:
        # Prompt for credentials and validate connection
        get_connection_from_user()
        engine = get_db_engine()
        
        print("\n🧹 Executing database wipe...")
        with engine.connect() as conn:
            try:
                # Try TRUNCATE first for a complete serial sequence reset
                with conn.begin():
                    conn.execute(text("""
                        TRUNCATE TABLE 
                            log_classifications, 
                            youtube_history, 
                            search_history, 
                            interest_categories 
                        RESTART IDENTITY CASCADE;
                    """))
                print("✅ Tables truncated successfully.")
            except Exception as truncate_err:
                print(f"⚠️ TRUNCATE blocked by open PgBouncer connection pool: {truncate_err}")
                print("🔄 Falling back to pool-compatible DELETE commands...")
                # Fall back to safe DELETE queries which don't require ACCESS EXCLUSIVE locks
                with conn.begin():
                    conn.execute(text("DELETE FROM log_classifications;"))
                    conn.execute(text("DELETE FROM youtube_history;"))
                    conn.execute(text("DELETE FROM search_history;"))
                    conn.execute(text("DELETE FROM interest_categories;"))
                print("✅ Tables deleted successfully.")
                
        print("\n" + "=" * 60)
        print("  🎉 DATABASE SUCCESSFULLY RESET & WIPED CLEAN!")
        print("=" * 60)
        print("\nNext Steps:")
        print("  1. Start the FastAPI server (python app.py) to automatically re-seed taxonomy.")
        print("  2. Ingest your Chrome history or Google Takeout files cleanly from the Flutter UI!")
        print("  3. Your vector search index is ready to be loaded with fresh data!")
        print("=" * 60 + "\n")
        
    except Exception as e:
        print(f"\n❌ ERROR: Database wipe failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
