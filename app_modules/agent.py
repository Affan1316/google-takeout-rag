import urllib.parse
import json
from sqlalchemy import text, create_engine
from langchain_core.tools import tool
from langchain_community.utilities.sql_database import SQLDatabase
from langchain_community.agent_toolkits.sql.toolkit import SQLDatabaseToolkit
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

from .state import DBState, EmbeddingState, system_instruction
from .database import verify_and_initialize_db

@tool
def semantic_youtube_search(concept: str) -> str:
    """Use this tool when the user asks to find YouTube videos by meaning, concept, topic, or similarity."""
    if not DBState.engine:
        return "Database not connected. Please upload a CSV with credentials first."
        
    embeddings_model = EmbeddingState.get_model()
    # 1. Turn the user's concept into a 384-dimensional vector
    query_vector = embeddings_model.embed_query(concept)
    
    # 2. Use pgvector to find the 5 closest matches using Cosine Distance (<=>)
    with DBState.engine.connect() as conn:
        result = conn.execute(
            text("""
                SELECT video_title, channel_title 
                FROM youtube_history 
                WHERE embedding IS NOT NULL
                ORDER BY embedding <=> :vec 
                LIMIT 5;
            """),
            {"vec": str(query_vector)}
        )
        rows = result.fetchall()

    if not rows:
        return "No conceptually similar videos found."

    return "Semantically related videos found: " + " | ".join([f"'{r[0]}' by {r[1]}" for r in rows])

@tool
def generate_longitudinal_report(timezone: str = 'Asia/Karachi') -> str:
    """Use this tool when the user asks for a broad, chronological report of their interests over time, or asks how their habits have evolved over the years."""
    if not DBState.engine:
        return "Database not connected."
        
    try:
        import pandas as pd
        import numpy as np
        
        # 1. Fetch raw interaction metrics
        with DBState.engine.connect() as conn:
            query = text("""
                WITH all_logs AS (
                    SELECT 
                        yh.timestamp AT TIME ZONE :tz AS local_time,
                        lc.category_id
                    FROM log_classifications lc
                    JOIN youtube_history yh ON lc.youtube_log_id = yh.id
                    WHERE lc.youtube_log_id IS NOT NULL
                    UNION ALL
                    SELECT 
                        sh.timestamp AT TIME ZONE :tz AS local_time,
                        lc.category_id
                    FROM log_classifications lc
                    JOIN search_history sh ON lc.search_log_id = sh.id
                    WHERE lc.search_log_id IS NOT NULL
                )
                SELECT 
                    DATE_TRUNC('month', local_time) AS log_month,
                    ic.category_name,
                    COUNT(*) as interaction_count
                FROM all_logs
                JOIN interest_categories ic ON all_logs.category_id = ic.id
                GROUP BY log_month, ic.category_name
            """)
            rows = conn.execute(query, {"tz": timezone}).fetchall()
            
        if not rows:
            return "No historical classifications found to generate a longitudinal report."
            
        # 2. Compile metrics in Pandas
        df = pd.DataFrame(rows, columns=['month', 'category', 'count'])
        df['month'] = pd.to_datetime(df['month'])
        df = df.sort_values(['month', 'count'], ascending=[True, False])
        
        # Total interactions over time
        total_interactions = int(df['count'].sum())
        month_counts = df.groupby('month')['count'].sum()
        active_months = len(month_counts)
        
        # Pivot to create a monthly category matrix
        pivot_df = df.pivot(index='month', columns='category', values='count').fillna(0)
        
        # Compute Month-over-Month (MoM) Deltas
        deltas = pivot_df.diff().fillna(0)
        
        # Identify top anomalies / surges (greatest MoM increases)
        surges = []
        for col in deltas.columns:
            max_surge_val = deltas[col].max()
            if max_surge_val > 10:  # Only report meaningful surges
                max_month = deltas[col].idxmax()
                surges.append({
                    "category": col,
                    "surge_size": int(max_surge_val),
                    "month": max_month.strftime('%Y-%m'),
                    "previous_count": int(pivot_df.loc[max_month, col] - max_surge_val)
                })
        surges = sorted(surges, key=lambda x: x['surge_size'], reverse=True)[:5]
        
        # Identify interest decay (greatest drops)
        declines = []
        for col in deltas.columns:
            max_decline_val = deltas[col].min()
            if max_decline_val < -10:
                min_month = deltas[col].idxmin()
                declines.append({
                    "category": col,
                    "decline_size": int(abs(max_decline_val)),
                    "month": min_month.strftime('%Y-%m')
                })
        declines = sorted(declines, key=lambda x: x['decline_size'], reverse=True)[:5]
        
        # Year-by-Year Peak Summaries
        df['year'] = df['month'].dt.year
        yearly_df = df.groupby(['year', 'category'])['count'].sum().reset_index()
        yearly_df = yearly_df.sort_values(['year', 'count'], ascending=[True, False])
        
        yearly_peaks = {}
        for yr in yearly_df['year'].unique():
            yr_subset = yearly_df[yearly_df['year'] == yr]
            top_cat = yr_subset.iloc[0]['category']
            top_count = int(yr_subset.iloc[0]['count'])
            
            # Fetch representative titles for the peak category of that year
            # (Limit to 2 to keep context ultra-tight)
            with DBState.engine.connect() as conn:
                highlight_query = text("""
                    WITH all_logs AS (
                        SELECT 
                            yh.video_title AS log_text,
                            yh.timestamp AT TIME ZONE :tz AS local_time,
                            lc.category_id
                        FROM log_classifications lc
                        JOIN youtube_history yh ON lc.youtube_log_id = yh.id
                        WHERE lc.youtube_log_id IS NOT NULL
                        UNION ALL
                        SELECT 
                            sh.page_title AS log_text,
                            sh.timestamp AT TIME ZONE :tz AS local_time,
                            lc.category_id
                        FROM log_classifications lc
                        JOIN search_history sh ON lc.search_log_id = sh.id
                        WHERE lc.search_log_id IS NOT NULL
                    )
                    SELECT al.log_text
                    FROM all_logs al
                    JOIN interest_categories ic ON al.category_id = ic.id
                    WHERE ic.category_name = :cat_name 
                      AND EXTRACT(YEAR FROM al.local_time) = :year
                      AND al.log_text IS NOT NULL AND al.log_text != ''
                    LIMIT 2
                """)
                h_rows = conn.execute(highlight_query, {"tz": timezone, "cat_name": top_cat, "year": int(yr)}).fetchall()
                
            yearly_peaks[str(yr)] = {
                "top_category": top_cat,
                "yearly_cat_interactions": top_count,
                "representative_topics": [r[0] for r in h_rows if r[0]]
            }
            
        summary = {
            "total_system_interactions": total_interactions,
            "span_of_active_months": active_months,
            "yearly_interest_hubs": yearly_peaks,
            "greatest_interest_surges_mom": surges,
            "greatest_interest_declines_mom": declines
        }
        
        return "Here is the compiled Pandas longitudinal analysis. Synthesize this delta and surge analysis into a highly detailed psychological/interest evolution report:\n" + json.dumps(summary, indent=2)
    except Exception as e:
        return f"Error generating longitudinal report: {str(e)}"

@tool
def get_top_visited_domains(limit: int = 10, start_date: str = None, end_date: str = None) -> str:
    """Use this tool to find the user's most visited website domains. You can optionally filter by a date range (start_date and end_date in 'YYYY-MM-DD' format)."""
    if not DBState.engine:
        return "Database not connected."
    try:
        filters = []
        params = {"limit": limit}
        if start_date:
            filters.append("timestamp >= :start_date")
            params["start_date"] = start_date
        if end_date:
            filters.append("timestamp <= :end_date")
            params["end_date"] = end_date
            
        filter_sql = " AND ".join(filters)
        if filter_sql:
            filter_sql = "WHERE " + filter_sql
            
        query = text(f"""
            SELECT actual_website, COUNT(*) as visit_count 
            FROM search_history 
            {filter_sql}
            GROUP BY actual_website 
            ORDER BY visit_count DESC 
            LIMIT :limit
        """)
        
        with DBState.engine.connect() as conn:
            rows = conn.execute(query, params).fetchall()
            
        if not rows:
            return "No visited domains found within specified filters."
        return "Top visited domains:\n" + "\n".join([f"• {r[0]}: {r[1]} visits" for r in rows if r[0]])
    except Exception as e:
        return f"Error fetching top domains: {str(e)}"

@tool
def get_daily_activity_counts(start_date: str = None, end_date: str = None) -> str:
    """Use this tool to get daily interaction volumes for YouTube watch logs and Google searches. Filters by start_date and end_date ('YYYY-MM-DD')."""
    if not DBState.engine:
        return "Database not connected."
    try:
        filters = []
        params = {}
        if start_date:
            filters.append("timestamp >= :start_date")
            params["start_date"] = start_date
        if end_date:
            filters.append("timestamp <= :end_date")
            params["end_date"] = end_date
            
        filter_sql = " AND ".join(filters)
        if filter_sql:
            filter_sql = "WHERE " + filter_sql
            
        query = text(f"""
            WITH daily_logs AS (
                SELECT DATE(timestamp) as log_day, 'Search' as service FROM search_history {filter_sql}
                UNION ALL
                SELECT DATE(timestamp) as log_day, 'YouTube' as service FROM youtube_history {filter_sql}
            )
            SELECT log_day, service, COUNT(*) as count 
            FROM daily_logs 
            GROUP BY log_day, service 
            ORDER BY log_day ASC, service ASC
        """)
        
        with DBState.engine.connect() as conn:
            rows = conn.execute(query, params).fetchall()
            
        if not rows:
            return "No activity logs found for the specified filters."
        return "Daily activity stats:\n" + "\n".join([f"• {r[0]} ({r[1]}): {r[2]} interactions" for r in rows])
    except Exception as e:
        return f"Error fetching activity counts: {str(e)}"

@tool
def search_history_by_keyword(keyword: str, limit: int = 15) -> str:
    """Use this tool to search for specific web pages, videos, or search queries using keyword matching on page titles, video titles, or URLs."""
    if not DBState.engine:
        return "Database not connected."
    try:
        query = text("""
            WITH matches AS (
                SELECT timestamp, page_title as title, actual_website as source, 'Search' as service, links FROM search_history WHERE page_title ILIKE :kw OR actual_website ILIKE :kw
                UNION ALL
                SELECT timestamp, video_title as title, channel_title as source, 'YouTube' as service, links FROM youtube_history WHERE video_title ILIKE :kw OR channel_title ILIKE :kw
            )
            SELECT timestamp, service, title, source, links 
            FROM matches 
            ORDER BY timestamp DESC 
            LIMIT :limit
        """)
        
        with DBState.engine.connect() as conn:
            rows = conn.execute(query, {"kw": f"%{keyword}%", "limit": limit}).fetchall()
            
        if not rows:
            return f"No logs found matching keyword: '{keyword}'."
        return f"Found matching history records (up to {limit}):\n" + "\n".join([
            f"• [{r[0]}] {r[1]} - '{r[2]}' on {r[3]} ({r[4]})" for r in rows
        ])
    except Exception as e:
        return f"Error searching history: {str(e)}"

def init_db_and_agent(project_ref, password, host, port, llm_api_key):
    """Initializes the DB connection and LangGraph agent dynamically"""
    # 1. Robust validation of inputs
    if not project_ref:
        raise ValueError("Database Project Reference (project_ref) cannot be empty.")
    if not password:
        raise ValueError("Database Password cannot be empty.")
    if not host:
        raise ValueError("Database Host cannot be empty.")
    if not port:
        raise ValueError("Database Port cannot be empty.")
    if not llm_api_key:
        raise ValueError("LLM API Key cannot be empty.")

    safe_password = urllib.parse.quote_plus(password)
    DB_URI = f"postgresql://postgres.{project_ref}:{safe_password}@{host}:{port}/postgres"
    
    # 2. Construct SQLAlchemy engine
    DBState.engine = create_engine(
        DB_URI,
        pool_pre_ping=True,
        pool_recycle=300,
        pool_size=10,
        max_overflow=20
    )
    
    # 3. Connection pre-flight validation
    try:
        with DBState.engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as e:
        DBState.engine = None
        raise ValueError(f"Database connection failed. Please check your credentials and network. Details: {e}")
    
    # Run auto-migration & seeding verification
    verify_and_initialize_db(DBState.engine)
    
    db = SQLDatabase(DBState.engine)
    
    # Initialize LLM dynamically with the user's API Key
    llm = ChatOpenAI(
        api_key=llm_api_key,
        base_url="https://api.deepseek.com",
        model="deepseek-chat",
        temperature=0
    )
    
    toolkit = SQLDatabaseToolkit(db=db, llm=llm)
    tools = toolkit.get_tools() + [
        semantic_youtube_search, 
        generate_longitudinal_report,
        get_top_visited_domains,
        get_daily_activity_counts,
        search_history_by_keyword
    ]
    
    DBState.agent_executor = create_react_agent(model=llm, tools=tools, prompt=system_instruction)
    
    DBState.project_ref = project_ref
    DBState.password = password
    DBState.host = host
    DBState.port = port
    DBState.llm_api_key = llm_api_key
    print("✅ Database and Agent successfully initialized!")
