import os
from sqlalchemy import text
from langchain_huggingface import HuggingFaceEmbeddings
from db_config import get_connection_from_user, get_db_engine

# A granular, hierarchical taxonomy for digital activity
TAXONOMY = {
    "Software Engineering": [
        "Machine Learning & AI",
        "Frontend & UI Development",
        "Backend Architecture",
        "Mobile App Development",
        "DevOps & Deployment",
        "Python Programming",
        "Database Optimization"
    ],
    "Productivity & Optimization": [
        "Time Management",
        "Note Taking & Zettelkasten",
        "Focus & Deep Work",
        "Workflow Automation"
    ],
    "Science & Technology": [
        "Cyberpsychology",
        "Hardware & Gadgets",
        "Space & Physics",
        "Cybersecurity"
    ],
    "Entertainment & Leisure": [
        "Video Games & Let's Plays",
        "Movie & TV Reviews",
        "Comedy & Satire",
        "Music & Concerts"
    ],
    "Finance & Business": [
        "Stock Trading & Investing",
        "Entrepreneurship",
        "Cryptocurrency",
        "Personal Finance"
    ],
    "Health & Lifestyle": [
        "Fitness & Workouts",
        "Nutrition & Cooking",
        "Mental Health & Mindfulness",
        "Travel & Vlogs"
    ]
}

def seed_categories():
    try:
        print("="*60)
        print("🌱 SEEDING INTEREST TAXONOMY")
        print("="*60)
        
        # 1. Connect to DB
        get_connection_from_user()
        engine = get_db_engine()
        
        # 2. Load the Embedding Model (same one used in app.py)
        print("\nLoading BAAI/bge-small-en-v1.5 embedding model (this may take a moment)...")
        embeddings_model = HuggingFaceEmbeddings(
            model_name="BAAI/bge-small-en-v1.5",
            encode_kwargs={'normalize_embeddings': True}
        )
        print("✅ Model loaded successfully.")
        
        with engine.connect() as conn:
            # Check if already seeded to prevent duplicates
            result = conn.execute(text("SELECT COUNT(*) FROM interest_categories")).scalar()
            if result > 0:
                print(f"⚠️ Found {result} categories already in the database.")
                override = input("Do you want to clear them and re-seed? (y/n): ")
                if override.lower() == 'y':
                    conn.execute(text("DELETE FROM interest_categories"))
                    conn.commit()
                    print("Cleared existing categories.")
                else:
                    print("Aborting seed operation.")
                    return

            total_inserted = 0
            
            # 3. Insert Taxonomy
            for parent_cat, sub_cats in TAXONOMY.items():
                # Generate embedding for parent category
                print(f"\nProcessing Parent: {parent_cat}")
                parent_vector = embeddings_model.embed_query(parent_cat)
                
                # Insert Parent
                res = conn.execute(
                    text("""
                        INSERT INTO interest_categories (category_name, embedding, is_global, parent_id)
                        VALUES (:name, :vec, true, NULL)
                        RETURNING id
                    """),
                    {"name": parent_cat, "vec": str(parent_vector)}
                )
                parent_id = res.scalar()
                total_inserted += 1
                
                # Insert Sub-categories
                for sub_cat in sub_cats:
                    sub_vector = embeddings_model.embed_query(sub_cat)
                    conn.execute(
                        text("""
                            INSERT INTO interest_categories (category_name, embedding, is_global, parent_id)
                            VALUES (:name, :vec, true, :parent)
                        """),
                        {"name": sub_cat, "vec": str(sub_vector), "parent": parent_id}
                    )
                    total_inserted += 1
                    print(f"  └─ Inserted Sub-category: {sub_cat}")
            
            conn.commit()
            print(f"\n🎉 Successfully seeded {total_inserted} hierarchical categories into the database!")

    except Exception as e:
        print(f"\n❌ Error seeding categories: {e}")

if __name__ == "__main__":
    seed_categories()
