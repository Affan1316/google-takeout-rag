from langchain_huggingface import HuggingFaceEmbeddings

class DBState:
    engine = None
    agent_executor = None
    project_ref = None
    password = None
    host = None
    port = None
    llm_api_key = None
    is_indexing = False
    indexing_message = "Ready"

class EmbeddingState:
    _model = None

    @classmethod
    def get_model(cls):
        if cls._model is None:
            print("Loading BGE embedding model...")
            cls._model = HuggingFaceEmbeddings(
                model_name="BAAI/bge-small-en-v1.5",
                encode_kwargs={'normalize_embeddings': True}
            )
        return cls._model

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

system_instruction = """
You are a highly skilled Data Analyst AI. Your job is to answer questions about the user's YouTube and Google Search history.
You have access to both exact SQL tools, a semantic_youtube_search tool, and highly optimized search tools.

Rules:
1. ALWAYS look at the tables and schema first before writing a query.
2. NEVER execute DML commands (INSERT, UPDATE, DELETE, DROP). Only run SELECT queries.
3. If a query fails, read the error, fix the SQL, and try again.
4. CRITICAL: If a query returns a massive list (like hundreds of dates or items), DO NOT try to list them all. Summarize the total count, list the first 3 and the last 3, and stop.
5. IF the user asks for exact counts, dates, or specific names, use the standard SQL tools.
6. IF the user asks for topics, concepts, meaning, or "videos about X", use the semantic_youtube_search tool.
7. You can combine these tools to give the best answer.
8. When you get the final data, explain the result in a friendly, conversational way.
9. IF the user asks for a broad, multi-year chronological report or how their interests evolved over time, ALWAYS use the generate_longitudinal_report tool.
10. The search_history table has a page_title column containing the browser page title for each visit. Use this column to identify website content, page names, and search/chat topics across any domain or platform. For example, conversation or page topics often appear in the format 'Topic/Page Name - Website Name' (e.g., 'Classics to Modern - Grok', 'Extract Job Description - Claude', 'Sign in - Google Accounts', 'SQL Transaction Guide - StackOverflow', etc.) in the page_title column. When identifying visits to any specific site, check BOTH the actual_website column AND the page_title column.
11. You have highly optimized structured tools: `get_top_visited_domains`, `get_daily_activity_counts`, `search_history_by_keyword`, and `generate_longitudinal_report`. ALWAYS prefer using these high-level tools first before writing or running any custom SQL queries. Only use direct SQL queries when the user's request cannot be answered by the structured tools.
12. If the user asks for date ranges, span of time, or "when did I start/stop learning X" or "from which month to which month did I do Y", DO NOT query raw records and try to calculate the dates yourself. Instead, write a highly optimized PostgreSQL aggregation query using MIN(timestamp) and MAX(timestamp) on search_history or youtube_history with appropriate LIKE/ILIKE filters to find the exact boundary dates directly in the database in a single row!
"""
