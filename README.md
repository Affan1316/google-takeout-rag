# History AI Agent — App Manual & Concepts

> A thesis-style technical manual documenting the architecture, design rationale, and operational guide for a full-stack Retrieval-Augmented Generation (RAG) system that transforms raw Google Takeout data into a queryable, self-evolving digital psychology profile.

---

## Table of Contents

1. [What This System Does](#1-what-this-system-does)
2. [System Architecture Overview](#2-system-architecture-overview)
3. [Why RAG? — The Core Thesis](#3-why-rag--the-core-thesis)
4. [Backend: Design Decisions & Rationale](#4-backend-design-decisions--rationale)
5. [Frontend: Design Decisions & Rationale](#5-frontend-design-decisions--rationale)
6. [The Ingestion Pipeline — Step by Step](#6-the-ingestion-pipeline--step-by-step)
7. [The RAG Query Engine — How Questions Are Answered](#7-the-rag-query-engine--how-questions-are-answered)
8. [Taxonomy Drift — The Self-Evolving Interest Model](#8-taxonomy-drift--the-self-evolving-interest-model)
9. [Chat History Persistence — Local Storage Architecture](#9-chat-history-persistence--local-storage-architecture)
10. [User Manual: Getting Started](#10-user-manual-getting-started)
11. [API Reference](#11-api-reference)
12. [Troubleshooting](#12-troubleshooting)
13. [File Map & Architecture Diagram](#13-file-map--architecture-diagram)

---

## 1. What This System Does

This application takes your **raw Google Takeout data** — years of YouTube watch history and Google Search activity — and transforms it into an intelligent, conversational knowledge base you can query in natural language.

Instead of scrolling through thousands of CSV rows, you ask questions like:

- *"What was I most interested in during 2022?"*
- *"Find videos about machine learning I watched"*
- *"How have my interests evolved over the past 3 years?"*
- *"Which YouTube channels did I watch the most?"*

The system answers using a combination of **exact SQL queries** (for counts, dates, specific titles) and **semantic vector search** (for conceptual/meaning-based queries), orchestrated by an LLM agent that decides which tool to use for each question.

---

## 2. System Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                     FLUTTER DESKTOP APP                         │
│  ┌──────────┐  ┌──────────────┐  ┌───────────────────────────┐ │
│  │ Chat UI  │  │ Upload Dialog│  │ Navigation Drawer         │ │
│  │ (Markdown│  │ (CSV/HTML)   │  │ (Multi-Session History)   │ │
│  │  Render) │  │              │  │                           │ │
│  └────┬─────┘  └──────┬───────┘  └────────────┬──────────────┘ │
│       │               │                       │                │
│       │      HTTP/REST over localhost          │                │
│       ▼               ▼                       ▼                │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              Local JSON Document Store                  │   │
│  │              (chat_sessions.json via path_provider)     │   │
│  └─────────────────────────────────────────────────────────┘   │
└────────────────────────┬───────────────────────────────────────┘
                         │ HTTP
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                     FASTAPI BACKEND (Python)                    │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │ LangGraph    │  │ BGE-small    │  │ CSV/HTML Processor   │  │
│  │ ReAct Agent  │  │ Embeddings   │  │ + YouTube Enrichment │  │
│  │ (DeepSeek)   │  │ (HuggingFace)│  │                      │  │
│  └──────┬───────┘  └──────┬───────┘  └──────────┬───────────┘  │
│         │                 │                      │              │
│         ▼                 ▼                      ▼              │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              Supabase PostgreSQL + pgvector              │   │
│  │  youtube_history │ search_history │ interest_categories  │   │
│  │  log_classifications │ HNSW Index (384-dim)             │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. Why RAG? — The Core Thesis

### 3.1 The Problem with Raw Data

Google Takeout exports are massive, flat data dumps. A typical export contains thousands of rows like:

```
YouTube, Watched, 2023-05-12T14:30:00Z, https://www.youtube.com/watch?v=abc123
```

This tells you *what* happened, but not *what it means*. You can't ask "what was I interested in?" because the data has no concept of interests, categories, or evolution over time.

### 3.2 Why Not Just Upload to ChatGPT/Claude?

A naive approach — copying your raw HTML/CSV into a chat window — fails for three fundamental reasons:

| Problem | Impact |
|---------|--------|
| **Context window limits** | GPT-4 handles ~128K tokens. A year of YouTube history easily exceeds 500K tokens. The LLM simply can't read it all. |
| **No persistent memory** | Each conversation starts fresh. You'd have to re-upload every time. The LLM forgets everything between sessions. |
| **No structured querying** | LLMs can't efficiently count, sort, or filter thousands of rows. Asking "how many videos did I watch in March 2023?" requires SQL-like precision, not language generation. |

### 3.3 The RAG Solution

RAG (Retrieval-Augmented Generation) solves all three:

1. **Structured storage** — Data lives in a PostgreSQL database with proper schemas, indexes, and types. SQL handles exact queries with perfect precision.
2. **Semantic search** — Every record is converted into a 384-dimensional vector embedding. When you ask about "machine learning", the system finds videos about "neural networks", "deep learning", and "AI training" — even though those words never appear in your query.
3. **Agent orchestration** — A LangGraph ReAct agent decides *which tool to use* for each question. Exact counts → SQL. Conceptual queries → vector search. Broad evolution reports → longitudinal analysis tool. The LLM reasons about the question, selects the right tool, interprets the result, and generates a natural-language answer.

### 3.4 Why This Architecture Beats Alternatives

| Alternative | Why We Didn't Use It |
|------------|---------------------|
| **Pinecone/Weaviate** (dedicated vector DB) | Requires a separate paid service. Supabase pgvector gives us SQL + vectors in one free database — no additional infrastructure. |
| **ChromaDB** (local vector DB) | No SQL querying. You can't run `SELECT COUNT(*) WHERE timestamp > '2023-01-01'` in Chroma. We need both structured AND semantic access. |
| **LangChain ConversationalRetrievalChain** | Too rigid. Our agent needs to dynamically choose between 4+ tools (SQL, semantic search, longitudinal report, schema inspection). LangGraph's ReAct pattern handles this naturally. |
| **Fine-tuning an LLM** | Destroys the ability to add new data. Every CSV upload would require retraining. RAG keeps the knowledge in the database, not in model weights. |

---

## 4. Backend: Design Decisions & Rationale

### 4.1 Why DeepSeek Over OpenAI?

The LLM powering the RAG agent is **DeepSeek Chat** (`deepseek-chat`), accessed via the OpenAI-compatible API at `api.deepseek.com`.

| Factor | DeepSeek | OpenAI GPT-4 |
|--------|----------|---------------|
| **Cost** | ~$0.14/M input tokens | ~$30/M input tokens |
| **SQL reasoning** | Excellent — trained on code-heavy datasets | Excellent |
| **API compatibility** | 100% OpenAI SDK compatible | Native |
| **Speed** | Fast inference | Comparable |

DeepSeek provides GPT-4-class reasoning for SQL generation and tool selection at **~200× lower cost**. Since the agent's job is structured reasoning (not creative writing), the quality difference is negligible. The `langchain_openai.ChatOpenAI` client connects seamlessly by simply overriding `base_url`.

### 4.2 Why BGE-small-en-v1.5 for Embeddings?

We use `BAAI/bge-small-en-v1.5` from HuggingFace, running locally on CPU.

| Factor | BGE-small | OpenAI ada-002 | Cohere embed |
|--------|-----------|-----------------|--------------|
| **Dimensions** | 384 | 1536 | 1024 |
| **Cost** | Free (local) | $0.10/M tokens | $0.10/M tokens |
| **Network required?** | No | Yes | Yes |
| **Storage per vector** | 1.5 KB | 6 KB | 4 KB |
| **Quality (MTEB)** | 62.x | 63.x | 64.x |

**Why local?** Embedding thousands of records on every CSV upload would be expensive with a paid API. BGE-small runs entirely on your CPU, costs nothing, and produces high-quality 384-dimensional normalized vectors. The 384-dim vectors also consume 4× less database storage than ada-002's 1536-dim vectors, which matters when you have tens of thousands of records.

**Why normalized?** `encode_kwargs={'normalize_embeddings': True}` ensures all vectors have unit length. This makes cosine distance (`<=>` in pgvector) equivalent to inner product, which is computationally cheaper and produces cleaner similarity scores.

### 4.3 Why Supabase PostgreSQL + pgvector?

We use Supabase's managed PostgreSQL with the `pgvector` extension.

**The key insight:** Our data is inherently *relational AND semantic*. A YouTube watch event has structured fields (timestamp, channel, view count) AND a conceptual meaning (the video's topic). We need both access patterns in a single query.

pgvector lets us write queries like:
```sql
-- Find conceptually similar videos watched after January 2023
SELECT video_title, channel_title
FROM youtube_history
WHERE embedding IS NOT NULL
  AND timestamp > '2023-01-01'
ORDER BY embedding <=> :query_vector
LIMIT 5;
```

No dedicated vector database can do this — they can't filter by timestamp, join with classification tables, or aggregate counts. pgvector gives us the best of both worlds in a single `SELECT`.

### 4.4 Why HNSW Index with ef_construction=256?

The vector index on `interest_categories` uses:
```sql
CREATE INDEX interest_categories_embedding_idx
ON interest_categories USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 256);
```

**Why HNSW over IVFFlat?**
- IVFFlat requires a training step (`CREATE INDEX` scans the entire table to build centroids). If you add categories later, the centroids become stale and recall degrades. You'd need to rebuild the index.
- HNSW is self-balancing. New categories are dynamically inserted into the graph. No retraining needed — critical for our taxonomy drift feature where categories are added at runtime.

**Why ef_construction=256?**
The `interest_categories` table is small (30-50 rows), but classification accuracy is critical — every raw log is classified by finding its nearest category embedding. With `ef_construction=256` (vs. the default 64), the HNSW graph is built with 4× more candidate neighbors during construction, producing near-perfect recall. The build time penalty is negligible on a 50-row table.

### 4.5 Why LangGraph ReAct Agent? — A Deep Dive

This is the **intellectual core** of the entire system. Everything else — the database schema, the embeddings, the Flutter UI — exists to serve the agent. Understanding how it works, why it was designed this way, and what alternatives were rejected is essential to understanding the application.

#### 4.5.1 The ReAct Pattern — Theory

ReAct (Reason + Act), introduced by Yao et al. (2022), is a prompting paradigm where an LLM alternates between:

1. **Thought** — The LLM reasons about what information it needs and which tool would provide it
2. **Action** — The LLM invokes a tool with specific parameters
3. **Observation** — The tool's output is fed back to the LLM as new context
4. **Repeat** — The LLM decides whether to use another tool or produce a final answer

This creates a **dynamic execution graph** rather than a fixed pipeline. The number of steps, the tools used, and the order of operations are all decided at runtime by the LLM based on the specific question.

```
                    ┌─────────────────────┐
                    │   User Question     │
                    └──────────┬──────────┘
                               │
                    ┌──────────▼──────────┐
                ┌──►│   LLM Reasoning     │◄──┐
                │   │   (Thought Step)    │   │
                │   └──────────┬──────────┘   │
                │              │              │
                │   ┌──────────▼──────────┐   │
                │   │  Is answer ready?   │   │
                │   └──┬──────────────┬───┘   │
                │      │ No           │ Yes   │
                │   ┌──▼──────────┐   │       │
                │   │ Select Tool │   │       │
                │   │ + Arguments │   │       │
                │   └──────┬──────┘   │       │
                │          │          │       │
                │   ┌──────▼──────┐   │       │
                │   │ Execute     │   │       │
                │   │ Tool        │   │       │
                │   └──────┬──────┘   │       │
                │          │          │       │
                │   ┌──────▼──────┐   │       │
                └───┤ Observation │   │       │
                    │ (Tool Output)│  │       │
                    └─────────────┘   │       │
                                      │       │
                    ┌─────────────────▼───┐   │
                    │   Final Answer       │   │
                    └─────────────────────┘   │
                                              │
           (Multi-tool: loop back)────────────┘
```

**The key insight:** Traditional RAG systems follow a deterministic path — embed the query, retrieve the top-K documents, feed them to the LLM, generate an answer. This works for one type of question. But our system needs to handle fundamentally different question types (exact counts vs. conceptual searches vs. longitudinal analysis), and the agent must figure out *which type each question is* before deciding what to do.

#### 4.5.2 Why LangGraph Over LangChain AgentExecutor?

LangChain's older `AgentExecutor` (now deprecated) also implements ReAct, so why use LangGraph's `create_react_agent` instead?

| Factor | LangChain AgentExecutor | LangGraph ReAct Agent |
|--------|------------------------|----------------------|
| **Architecture** | Imperative Python loop | Declarative state graph (nodes + edges) |
| **State management** | Implicit (hidden in executor) | Explicit `MessagesState` — full message history accessible at every step |
| **Streaming** | Partial support | First-class streaming of intermediate steps and tool outputs |
| **Customizability** | Monkey-patching or subclassing | Add/remove/rewire nodes in the graph |
| **Error recovery** | Crashes on tool errors | LLM sees the error as an Observation and can self-correct |
| **Maintenance** | Deprecated by LangChain team | Actively maintained as the recommended replacement |

The critical advantage is **state graph architecture**. LangGraph models the agent as a directed graph:

```
                 ┌──────────┐
        ┌───────►│  Agent   │◄────────┐
        │        │  Node    │         │
        │        └────┬─────┘         │
        │             │               │
        │     ┌───────▼────────┐      │
        │     │  Should use    │      │
        │     │  tools?        │      │
        │     └───┬────────┬───┘      │
        │         │ Yes    │ No       │
        │    ┌────▼────┐   │          │
        │    │  Tool   │   │          │
        │    │  Node   │   │          │
        │    └────┬────┘   │          │
        │         │        │          │
        └─────────┘   ┌────▼────┐     │
                      │  END    │     │
                      └─────────┘     │
```

Each node in the graph is a pure function over `MessagesState` — a list of messages that grows as the agent works. The **Agent Node** calls the LLM. The **Tool Node** executes whichever tool the LLM selected. Edges route based on whether the LLM's response contains tool calls or a final answer. This makes the execution traceable, debuggable, and deterministic for the same input.

#### 4.5.3 Agent Construction — How It's Built

The agent is constructed in `init_db_and_agent()` with this code:

```python
# 1. Create the LLM client (DeepSeek via OpenAI-compatible API)
llm = ChatOpenAI(
    api_key=llm_api_key,
    base_url="https://api.deepseek.com",
    model="deepseek-chat",
    temperature=0          # ← Deterministic reasoning, no creativity
)

# 2. Get the SQL toolkit (auto-generates tools from the database schema)
toolkit = SQLDatabaseToolkit(db=db, llm=llm)

# 3. Merge SQL tools with our custom tools
tools = toolkit.get_tools() + [semantic_youtube_search, generate_longitudinal_report]

# 4. Build the agent graph
DBState.agent_executor = create_react_agent(
    model=llm,
    tools=tools,
    prompt=system_instruction    # ← The system prompt that governs behavior
)
```

**Why `temperature=0`?** The agent's job is *structured reasoning* — deciding which SQL query to write, which tool to call, how to interpret a result. This is a logic task, not a creative task. Temperature=0 makes the LLM's outputs maximally deterministic: given the same question and database state, the agent will produce the same tool selection and SQL queries every time. This is critical for reliability — you don't want the agent to "creatively" decide to skip the schema inspection step or write a different SQL query each run.

#### 4.5.4 The Complete Tool Inventory

The agent has access to **7 tools** — 5 from the SQL toolkit and 2 custom:

##### SQL Toolkit Tools (Auto-Generated by LangChain)

| # | Tool | What It Does | Why The Agent Needs It |
|---|------|--------------|-----------------------|
| 1 | `sql_db_list_tables` | Returns a comma-separated list of all table names | **Schema discovery.** The agent doesn't hardcode table names. It asks "what tables exist?" first, making it robust to schema changes. |
| 2 | `sql_db_schema` | Returns `CREATE TABLE` DDL with column names, types, and sample rows | **Column discovery.** The agent learns that `youtube_history` has `video_title`, `channel_title`, etc. Without this, it would guess column names and write invalid SQL. |
| 3 | `sql_db_query` | Executes a raw SQL `SELECT` query and returns formatted results | **The workhorse.** Every exact question ("how many?", "which?", "when?") is answered via SQL. Read-only — rejects INSERT/UPDATE/DELETE. |
| 4 | `sql_db_query_checker` | Passes SQL through the LLM to check for mistakes before execution | **Self-validation.** Catches wrong column names, missing WHERE clauses, or syntax errors *before* they hit the database. |
| 5 | `sql_db_list_tables` (info) | Provides additional metadata about tables | **Contextual understanding.** Helps the agent decide which tables are relevant. |

##### Custom Domain-Specific Tools

| # | Tool | What It Does | Why It Exists |
|---|------|--------------|--------------| 
| 6 | `semantic_youtube_search` | Embeds a concept into a 384-dim vector via BGE-small, runs pgvector `<=>` cosine distance to find the 5 most similar YouTube videos | **SQL can't do meaning.** "Find videos about cooking" via SQL `LIKE '%cooking%'` misses "Gordon Ramsay Tutorial" and "Making Pasta from Scratch". Vector similarity finds them by geometric proximity in 384-dimensional space. |
| 7 | `generate_longitudinal_report` | Builds a monthly category×count statistical matrix, extracts yearly top categories with 2 representative examples, returns compressed JSON | **LLM context management.** Years of raw data exceeds token limits. This tool pre-computes a 2-5KB summary the LLM synthesizes into a narrative evolution report. |

##### How Tool Selection Works — The Docstring Protocol

The LLM decides which tool to use based on the **tool's docstring**. LangGraph serializes each tool's name, parameter types, and docstring into the LLM's system context as a function schema.

Here are the actual docstrings from our codebase:

```python
@tool
def semantic_youtube_search(concept: str) -> str:
    """Use this tool when the user asks to find YouTube videos 
    by meaning, concept, topic, or similarity."""

@tool
def generate_longitudinal_report(timezone: str = 'Asia/Karachi') -> str:
    """Use this tool when the user asks for a broad, chronological 
    report of their interests over time, or asks how their habits 
    have evolved over the years."""
```

The docstrings are carefully written to act as **routing rules**. When the LLM sees "find videos about machine learning", it pattern-matches against "find YouTube videos by meaning, concept, topic, or similarity" and selects `semantic_youtube_search`. When it sees "how have my interests changed?", it matches "chronological report of their interests over time" and selects `generate_longitudinal_report`. For everything else (counts, dates, specific lookups), it falls through to the SQL tools.

**This is a form of natural language dispatch** — the LLM is essentially a router that reads function documentation and decides which function to call. The quality of the docstrings directly determines the quality of tool selection.

#### 4.5.5 The System Prompt — Behavioral Guardrails

The system prompt constrains the agent's behavior to prevent dangerous, wasteful, or confusing actions. Each of the 9 rules exists for a specific reason:

| Rule | Rationale |
|------|-----------|
| **1. Always inspect schema first** | Without this, the LLM guesses column names from training data ("title" vs "video_title"), producing SQL errors. Schema inspection guarantees correct column references. |
| **2. Never execute DML** | **Security critical.** The SQL toolkit technically allows any SQL. This rule prevents `DELETE FROM youtube_history` from malicious or confused prompts — defense-in-depth. |
| **3. Self-correct on errors** | SQL errors are inevitable. Without self-correction, one error terminates the conversation. With it, the agent reads the Postgres error, fixes the query, and retries (typically succeeds in 1-2 retries). |
| **4. Summarize massive results** | A naive `SELECT *` returning 10,000 rows would exceed the LLM's output token limit. This rule forces "Found 10,247 records. First 3: ... Last 3: ..." |
| **5-6. Tool routing hints** | Soft routing that complements docstrings: "exact counts → SQL", "concepts → semantic search". Reduces ambiguity for borderline questions. |
| **7. Tool combination** | Explicitly permits multi-tool turns. Without this, some LLMs default to one tool per question. |
| **8. Friendly tone** | Ensures raw SQL results are translated into natural language, not dumped as data tables. |
| **9. Longitudinal report routing** | The `generate_longitudinal_report` tool is expensive (3 complex SQL queries). This ensures it's only called for broad evolution questions, not "what did I watch yesterday?" |

#### 4.5.6 Traced Walkthrough — A Multi-Tool Query

Let's trace exactly what happens when the user asks:

> **"What cooking videos did I watch in 2023?"**

This requires *both* semantic understanding ("cooking" is a concept) *and* temporal filtering (year 2023):

```
STEP 1 → Agent reasons: "cooking" is semantic, not a column value.
         Let me check the schema first.
         Action: sql_db_list_tables()

STEP 2 → Tool returns: "youtube_history, search_history, 
         interest_categories, log_classifications"

STEP 3 → Agent reasons: Let me see youtube_history's columns.
         Action: sql_db_schema("youtube_history")

STEP 4 → Tool returns: CREATE TABLE youtube_history (
           id SERIAL, video_title TEXT, channel_title TEXT,
           timestamp TIMESTAMP, embedding VECTOR(384), ...)

STEP 5 → Agent reasons: I have video_title and timestamp columns.
         For "cooking" as a concept, I should use semantic search
         to find relevant titles, then SQL to filter by year.
         Action: semantic_youtube_search("cooking")

STEP 6 → Tool: [BGE-small embeds "cooking" → 384-dim vector]
         [pgvector <=> finds 5 nearest videos]
         Returns: "'Gordon Ramsay Beef Wellington' by GR | 
         'Making Pasta from Scratch' by Bon Appetit | ..."

STEP 7 → Agent reasons: Now I have cooking-related titles.
         Let me query for these specific titles in 2023.
         Action: sql_db_query("SELECT video_title, channel_title,
           timestamp FROM youtube_history
           WHERE video_title IN ('Gordon Ramsay...', ...)
           AND EXTRACT(YEAR FROM timestamp) = 2023
           ORDER BY timestamp")

STEP 8 → Tool returns: [('Making Pasta from Scratch', 
           'Bon Appetit', '2023-03-15'),
           ('Best Air Fryer Recipes 2023', 'Tasty', '2023-08-22')]

STEP 9 → Agent produces final answer:
         "Based on your history, I found 2 cooking-related
          videos you watched in 2023:
          1. Making Pasta from Scratch by Bon Appetit (March 2023)
          2. Best Air Fryer Recipes 2023 by Tasty (August 2023)"
```

**9 internal steps, 4 tool calls, 2 different tool types, all decided dynamically by the LLM.** A fixed chain could never produce this — it would either do SQL (missing "cooking" as a concept) or vector search (missing the 2023 temporal filter).

#### 4.5.7 The Message Protocol & UI Execution Trace Extraction

To provide full transparency, the system exposes the agent's intermediate steps (Thought-Action-Observation loop) directly to the user interface in a beautiful, collapsible timeline.

##### 1. Python Trace Parsing

Every agent invocation in `app.py` returns the full LangGraph state `messages` list. The backend extracts these steps using a sequential parsing loop:

```python
# Pass user's query into the LangGraph Agent
result = DBState.agent_executor.invoke({"messages": [("user", request.query)]})

# Extract the final AI response text
final_answer = result["messages"][-1].content

# Extract agent execution trace steps
steps = []
messages = result.get("messages", [])
i = 0
while i < len(messages):
    msg = messages[i]
    if msg.type == "ai" and getattr(msg, "tool_calls", None):
        thought = msg.content or ""
        actions = [{"name": tc.get("name"), "args": tc.get("args")} for tc in msg.tool_calls]
        
        # Gather all subsequent tool observations for this AI turn
        observations = []
        i += 1
        while i < len(messages) and messages[i].type == "tool":
            observations.append(messages[i].content)
            i += 1
        
        steps.append({
            "thought": thought,
            "actions": actions,
            "observations": observations
        })
        continue
    i += 1
```

This transforms the flat list of `MessagesState` elements into a structured JSON list:

```json
{
  "response": "Based on your history, you watched...",
  "steps": [
    {
      "thought": "Let me search for cooking videos first.",
      "actions": [{"name": "semantic_youtube_search", "args": {"query": "cooking"}}],
      "observations": ["Gordon Ramsay Beef Wellington..."]
    }
  ]
}
```

##### 2. Flutter JSON Document Persistence

The Flutter frontend (`main.dart`) maps this response into the `ChatMessage` model. Because we use a document-store model based on local JSON files (`chat_sessions.json`), the entire execution trace is serialized and persisted with 100% build reliability:

```dart
class ChatMessage {
  final String text;
  final bool isUser;
  final DateTime timestamp;
  final List<dynamic>? steps;

  // Serializes steps to local JSON file
  Map<String, dynamic> toJson() => {
    'text': text,
    'isUser': isUser,
    'timestamp': timestamp.toIso8601String(),
    'steps': steps,
  };
}
```

##### 3. User Interface Design & "Why Collapsible?"

In the chat UI, the trace is rendered using a custom `AgentTraceWidget` that displays a collapsible accordion titled `View Agent Execution Trace (N steps)`.

* **Design Rationale**: Displaying the full terminal logs and thoughts inline by default causes extreme visual noise, disrupting the conversational flow. Placing them inside an expandable section preserves a clean UI while giving power-users and developers instant access to the agent's exact SQL queries, parameters, and database observations.

The agent terminates when the LLM produces an `AIMessage` with `content` but no `tool_calls`. Every Thought, Action, and Observation is preserved — you can inspect `result["messages"]` to debug exactly what SQL was written, what the database returned, and how the LLM interpreted it. This transparency is impossible with black-box chain architectures.

#### 4.5.8 Error Self-Correction in Practice

When the agent writes bad SQL, the error becomes an Observation the LLM learns from:

```
Step 1: LLM writes:  SELECT titles FROM youtube_history LIMIT 5
Step 2: Tool returns: ERROR: column "titles" does not exist.
                      Hint: Perhaps you meant "video_title".
Step 3: LLM reasons: The column is called video_title, not titles.
Step 4: LLM writes:  SELECT video_title FROM youtube_history LIMIT 5
Step 5: Tool returns: [('Python Tutorial', ...), ...]
Step 6: LLM answers: Here are 5 videos from your history...
```

This is **why Rule 1 (always inspect schema first) exists** — if the agent checks `sql_db_schema` before writing SQL, it gets correct column names upfront and avoids the error-retry cycle. The rule is a performance optimization that prevents wasted LLM calls and database round-trips.

#### 4.5.9 Why Not Alternatives? — Detailed Comparison

| Architecture | How It Works | Why It Fails For Our Use Case |
|-------------|-------------|-------------------------------|
| **Naive RAG Chain** (embed → retrieve → generate) | Embeds the query, retrieves top-K similar documents, feeds to LLM | Cannot answer "how many videos did I watch?" — requires SQL `COUNT(*)`, not document retrieval |
| **SQL-only Agent** (text-to-SQL) | Converts natural language directly to SQL | Cannot answer "find videos about cooking" — SQL `LIKE` misses semantically similar results |
| **Multi-Chain Router** (classify → route) | Classifier LLM categorizes question type, routes to chain A or B | Fails on **combined queries** ("cooking videos in 2023") needing both semantic + SQL in sequence. A router picks one, not both |
| **Function Calling** (OpenAI-style) | LLM generates structured function calls in a single turn | Only calls tools *once per turn*. Our example requires 4 sequential calls where each output informs the next |
| **LangGraph ReAct Agent** ✅ | LLM reasons, acts, observes, repeats | Handles all question types, dynamically combines tools, self-corrects errors, no fixed path |


This is the **intellectual core** of the entire system. Everything else — the database schema, the embeddings, the Flutter UI — exists to serve the agent. Understanding how it works, why it was designed this way, and what alternatives were rejected is essential to understanding the application.

#### 4.5.1 The ReAct Pattern — Theory

ReAct (Reason + Act), introduced by Yao et al. (2022), is a prompting paradigm where an LLM alternates between:

1. **Thought** — The LLM reasons about what information it needs and which tool would provide it
2. **Action** — The LLM invokes a tool with specific parameters
3. **Observation** — The tool's output is fed back to the LLM as new context
4. **Repeat** — The LLM decides whether to use another tool or produce a final answer

This creates a **dynamic execution graph** rather than a fixed pipeline. The number of steps, the tools used, and the order of operations are all decided at runtime by the LLM based on the specific question.

```
                    ┌─────────────────────┐
                    │   User Question     │
                    └──────────┬──────────┘
                               │
                    ┌──────────▼──────────┐
                ┌──►│   LLM Reasoning     │◄──┐
                │   │   (Thought Step)    │   │
                │   └──────────┬──────────┘   │
                │              │              │
                │   ┌──────────▼──────────┐   │
                │   │  Is answer ready?   │   │
                │   └──┬──────────────┬───┘   │
                │      │ No           │ Yes   │
                │   ┌──▼──────────┐   │       │
                │   │ Select Tool │   │       │
                │   │ + Arguments │   │       │
                │   └──────┬──────┘   │       │
                │          │          │       │
                │   ┌──────▼──────┐   │       │
                │   │ Execute     │   │       │
                │   │ Tool        │   │       │
                │   └──────┬──────┘   │       │
                │          │          │       │
                │   ┌──────▼──────┐   │       │
                └───┤ Observation │   │       │
                    │ (Tool Output)│  │       │
                    └─────────────┘   │       │
                                      │       │
                    ┌─────────────────▼───┐   │
                    │   Final Answer       │   │
                    └─────────────────────┘   │
                                              │
           (Multi-tool: loop back)────────────┘
```

**The key insight:** Traditional RAG systems follow a deterministic path — embed the query, retrieve the top-K documents, feed them to the LLM, generate an answer. This works for one type of question. But our system needs to handle fundamentally different question types (exact counts vs. conceptual searches vs. longitudinal analysis), and the agent must figure out *which type each question is* before deciding what to do.

#### 4.5.2 Why LangGraph Over LangChain AgentExecutor?

LangChain's older `AgentExecutor` (now deprecated) also implements ReAct, so why use LangGraph's `create_react_agent` instead?

| Factor | LangChain AgentExecutor | LangGraph ReAct Agent |
|--------|------------------------|----------------------|
| **Architecture** | Imperative Python loop | Declarative state graph (nodes + edges) |
| **State management** | Implicit (hidden in executor) | Explicit `MessagesState` — full message history accessible at every step |
| **Streaming** | Partial support | First-class streaming of intermediate steps and tool outputs |
| **Customizability** | Monkey-patching or subclassing | Add/remove/rewire nodes in the graph |
| **Error recovery** | Crashes on tool errors | LLM sees the error as an Observation and can self-correct |
| **Maintenance** | Deprecated by LangChain team | Actively maintained as the recommended replacement |

The critical advantage is **state graph architecture**. LangGraph models the agent as a directed graph:

```
                 ┌──────────┐
        ┌───────►│  Agent   │◄────────┐
        │        │  Node    │         │
        │        └────┬─────┘         │
        │             │               │
        │     ┌───────▼────────┐      │
        │     │  Should use    │      │
        │     │  tools?        │      │
        │     └───┬────────┬───┘      │
        │         │ Yes    │ No       │
        │    ┌────▼────┐   │          │
        │    │  Tool   │   │          │
        │    │  Node   │   │          │
        │    └────┬────┘   │          │
        │         │        │          │
        └─────────┘   ┌────▼────┐     │
                      │  END    │     │
                      └─────────┘     │
```

Each node in the graph is a pure function over `MessagesState` — a list of messages that grows as the agent works. The **Agent Node** calls the LLM. The **Tool Node** executes whichever tool the LLM selected. Edges route based on whether the LLM's response contains tool calls or a final answer. This makes the execution traceable, debuggable, and deterministic for the same input.

#### 4.5.3 Agent Construction — How It's Built

The agent is constructed in `init_db_and_agent()` with this code:

```python
# 1. Create the LLM client (DeepSeek via OpenAI-compatible API)
llm = ChatOpenAI(
    api_key=llm_api_key,
    base_url="https://api.deepseek.com",
    model="deepseek-chat",
    temperature=0          # ← Deterministic reasoning, no creativity
)

# 2. Get the SQL toolkit (auto-generates tools from the database schema)
toolkit = SQLDatabaseToolkit(db=db, llm=llm)

# 3. Merge SQL tools with our custom tools
tools = toolkit.get_tools() + [semantic_youtube_search, generate_longitudinal_report]

# 4. Build the agent graph
DBState.agent_executor = create_react_agent(
    model=llm,
    tools=tools,
    prompt=system_instruction    # ← The system prompt that governs behavior
)
```

**Why `temperature=0`?** The agent's job is *structured reasoning* — deciding which SQL query to write, which tool to call, how to interpret a result. This is a logic task, not a creative task. Temperature=0 makes the LLM's outputs maximally deterministic: given the same question and database state, the agent will produce the same tool selection and SQL queries every time. This is critical for reliability — you don't want the agent to "creatively" decide to skip the schema inspection step or write a different SQL query each run.

#### 4.5.4 The Complete Tool Inventory

The agent has access to **7 tools** — 5 from the SQL toolkit and 2 custom:

##### SQL Toolkit Tools (Auto-Generated by LangChain)

| # | Tool | Signature | What It Does | Why The Agent Needs It |
|---|------|-----------|-------------|----------------------|
| 1 | `sql_db_list_tables` | `() → str` | Returns a comma-separated list of all table names in the database | **Schema discovery.** The agent doesn't hardcode table names. Before every SQL query, it first asks "what tables exist?" This makes the agent robust to schema changes — if you add a new table, the agent discovers it automatically. |
| 2 | `sql_db_schema` | `(table_names: str) → str` | Returns the `CREATE TABLE` DDL for the requested tables, including column names, types, and sample rows | **Column discovery.** The agent uses this to learn that `youtube_history` has columns like `video_title`, `channel_title`, `view_count`, etc. Without this, the agent would have to guess column names and would frequently write invalid SQL. The sample rows also help it understand data formats (e.g., timestamps are ISO 8601). |
| 3 | `sql_db_query` | `(query: str) → str` | Executes a raw SQL `SELECT` query and returns the result as a formatted string | **The workhorse.** Every exact question ("how many?", "which?", "when?", "top 5?") is answered by generating and executing SQL. The tool is read-only — it rejects INSERT/UPDATE/DELETE statements. |
| 4 | `sql_db_query_checker` | `(query: str) → str` | Passes a SQL query through the LLM to check for common mistakes before execution | **Self-validation.** Before running SQL, the agent can optionally validate it. This catches issues like wrong column names, missing WHERE clauses, or syntax errors *before* they hit the database. |
| 5 | `sql_db_list_tables` (info variant) | — | Provides additional metadata about tables | **Contextual understanding.** Helps the agent decide which tables are relevant for a given question. |

##### Custom Domain-Specific Tools

| # | Tool | Signature | What It Does | Why It Exists |
|---|------|-----------|-------------|---------------|
| 6 | `semantic_youtube_search` | `(concept: str) → str` | Embeds the concept string into a 384-dim vector using BGE-small, then runs a pgvector `<=>` cosine distance query to find the 5 most semantically similar YouTube videos | **SQL can't do meaning.** If the user asks "find videos about cooking", SQL `LIKE '%cooking%'` would miss "Gordon Ramsay Tutorial", "Making Pasta from Scratch", and "Kitchen Knife Review" — none of which contain the word "cooking". Vector similarity finds them because their embeddings are geometrically close in 384-dimensional space. |
| 7 | `generate_longitudinal_report` | `(timezone: str) → str` | Executes a complex multi-CTE SQL query that builds a monthly category×count statistical matrix across the user's entire history, extracts yearly top categories, fetches 2 representative log examples per year, and returns a compressed JSON package | **LLM context management.** Asking the LLM to analyze years of raw data would exceed token limits. This tool pre-computes the statistical summary and feeds the LLM a compressed data package (typically 2-5KB of JSON), which the LLM then synthesizes into a narrative report about how the user's interests evolved over time. |

##### How Tool Selection Works — The Docstring Protocol

The LLM decides which tool to use based on the **tool's docstring** (the Python function's documentation string). LangGraph serializes each tool's name, parameter types, and docstring into the LLM's system context as a function schema.

Here are the actual docstrings from our codebase:

```python
@tool
def semantic_youtube_search(concept: str) -> str:
    """Use this tool when the user asks to find YouTube videos 
    by meaning, concept, topic, or similarity."""

@tool
def generate_longitudinal_report(timezone: str = 'Asia/Karachi') -> str:
    """Use this tool when the user asks for a broad, chronological 
    report of their interests over time, or asks how their habits 
    have evolved over the years."""
```

The docstrings are carefully written to act as **routing rules**. When the LLM sees "find videos about machine learning", it pattern-matches against the docstring "find YouTube videos by meaning, concept, topic, or similarity" and selects `semantic_youtube_search`. When it sees "how have my interests changed?", it matches "chronological report of their interests over time" and selects `generate_longitudinal_report`. For everything else (counts, dates, specific lookups), it falls through to the SQL tools.

**This is a form of natural language dispatch** — the LLM is essentially a router that reads function documentation and decides which function to call. The quality of the docstrings directly determines the quality of tool selection.

#### 4.5.5 The System Prompt — Behavioral Guardrails

The system prompt is the most important piece of text in the entire application. It constrains the agent's behavior to prevent dangerous, wasteful, or confusing actions:

```python
system_instruction = """
You are a highly skilled Data Analyst AI. Your job is to answer 
questions about the user's YouTube and Google Search history.
You have access to both exact SQL tools and a semantic_youtube_search tool.

Rules:
1. ALWAYS look at the tables and schema first before writing a query.
2. NEVER execute DML commands (INSERT, UPDATE, DELETE, DROP). 
   Only run SELECT queries.
3. If a query fails, read the error, fix the SQL, and try again.
4. CRITICAL: If a query returns a massive list (like hundreds of 
   dates or items), DO NOT try to list them all. Summarize the 
   total count, list the first 3 and the last 3, and stop.
5. IF the user asks for exact counts, dates, or specific names, 
   use the standard SQL tools.
6. IF the user asks for topics, concepts, meaning, or "videos 
   about X", use the semantic_youtube_search tool.
7. You can combine these tools to give the best answer.
8. When you get the final data, explain the result in a friendly, 
   conversational way.
9. IF the user asks for a broad, multi-year chronological report 
   or how their interests evolved over time, ALWAYS use the 
   generate_longitudinal_report tool.
"""
```

Each rule exists for a specific reason:

| Rule | Rationale |
|------|-----------|
| **Rule 1:** Always inspect schema first | Without this, the LLM would guess column names from its training data ("title" instead of "video_title"), producing SQL errors. Inspecting the actual schema guarantees correct column references. |
| **Rule 2:** Never execute DML | **Security critical.** The SQL toolkit technically allows any SQL. Without this rule, a malicious or confused prompt could trigger `DELETE FROM youtube_history`. The rule creates a defense-in-depth layer beyond the toolkit's own restrictions. |
| **Rule 3:** Self-correct on errors | SQL errors are inevitable (wrong joins, type mismatches). Without self-correction, one error would terminate the conversation. With it, the agent reads the Postgres error message (e.g., "column 'titles' does not exist"), fixes the query (changes to `video_title`), and retries. This typically succeeds in 1-2 retries. |
| **Rule 4:** Summarize massive results | A naive `SELECT * FROM youtube_history` could return 10,000 rows. The LLM would attempt to include all of them in its response, exceeding its output token limit and producing truncated, useless output. This rule forces summarization: "Found 10,247 records. First 3: ... Last 3: ..." |
| **Rules 5-6:** Tool routing hints | These are soft routing hints that complement the tool docstrings. They tell the LLM "if the question sounds like X, prefer tool Y". This reduces ambiguity when a question could plausibly use either SQL or semantic search. |
| **Rule 7:** Tool combination | Explicitly grants permission to use multiple tools in one turn. Without this, some LLMs default to using exactly one tool per question. |
| **Rule 8:** Friendly tone | Ensures the raw SQL results or tool outputs are translated into natural language rather than dumped as raw data tables. |
| **Rule 9:** Longitudinal report routing | The `generate_longitudinal_report` tool is expensive (runs 3 complex SQL queries). This rule ensures it's only called for broad evolution questions, not for simple "what did I watch yesterday?" queries. |

#### 4.5.6 Traced Walkthrough — A Multi-Tool Query

Let's trace exactly what happens when the user asks:

> **"What cooking videos did I watch in 2023?"**

This question requires *both* semantic understanding ("cooking" is a concept, not a column value) *and* temporal filtering (year 2023). Here's the full agent execution:

```
┌─ STEP 1: Agent Node (LLM Reasoning) ────────────────────────┐
│                                                              │
│ Thought: The user wants cooking-related videos from 2023.    │
│ "Cooking" is a semantic concept, not a column value.         │
│ I should first check the database schema to understand       │
│ what columns are available.                                  │
│                                                              │
│ Action: sql_db_list_tables()                                 │
└──────────────────────────────────────────────────────────────┘
                         │
                         ▼
┌─ STEP 2: Tool Node ─────────────────────────────────────────┐
│ Output: "youtube_history, search_history,                    │
│          interest_categories, log_classifications"           │
└──────────────────────────────────────────────────────────────┘
                         │
                         ▼
┌─ STEP 3: Agent Node (LLM Reasoning) ────────────────────────┐
│                                                              │
│ Thought: I see youtube_history exists. Let me check its      │
│ schema to know the column names and types.                   │
│                                                              │
│ Action: sql_db_schema("youtube_history")                     │
└──────────────────────────────────────────────────────────────┘
                         │
                         ▼
┌─ STEP 4: Tool Node ─────────────────────────────────────────┐
│ Output: "CREATE TABLE youtube_history (                       │
│   id SERIAL, video_title TEXT, channel_title TEXT,            │
│   timestamp TIMESTAMP, embedding VECTOR(384), ...            │
│ )"                                                           │
│ Sample rows: [('Python Tutorial', 'Corey Schafer', ...)]     │
└──────────────────────────────────────────────────────────────┘
                         │
                         ▼
┌─ STEP 5: Agent Node (LLM Reasoning) ────────────────────────┐
│                                                              │
│ Thought: I can see there's a video_title column and a        │
│ timestamp column. For the "cooking" concept, I should use    │
│ the semantic_youtube_search tool. But that tool doesn't      │
│ filter by year. Let me use it to find cooking-related        │
│ video titles, then use SQL to filter by year.                │
│                                                              │
│ Action: semantic_youtube_search("cooking")                   │
└──────────────────────────────────────────────────────────────┘
                         │
                         ▼
┌─ STEP 6: Tool Node ─────────────────────────────────────────┐
│ [BGE-small embeds "cooking" → 384-dim vector]                │
│ [pgvector finds 5 nearest videos by cosine distance]         │
│                                                              │
│ Output: "Semantically related videos found:                  │
│   'Gordon Ramsay Beef Wellington' by GR |                    │
│   'Making Pasta from Scratch' by Bon Appetit |               │
│   'Kitchen Knife Sharpening Guide' by ChefSteps |            │
│   'Meal Prep for the Week' by Joshua Weissman |              │
│   'Best Air Fryer Recipes 2023' by Tasty"                    │
└──────────────────────────────────────────────────────────────┘
                         │
                         ▼
┌─ STEP 7: Agent Node (LLM Reasoning) ────────────────────────┐
│                                                              │
│ Thought: Now I have cooking-related video titles. Let me     │
│ query the database for these specific titles in 2023 to get  │
│ exact dates and view counts.                                 │
│                                                              │
│ Action: sql_db_query(                                        │
│   "SELECT video_title, channel_title, timestamp, view_count  │
│    FROM youtube_history                                      │
│    WHERE video_title IN ('Gordon Ramsay Beef Wellington',     │
│      'Making Pasta from Scratch', ...)                       │
│    AND EXTRACT(YEAR FROM timestamp) = 2023                   │
│    ORDER BY timestamp"                                       │
│ )                                                            │
└──────────────────────────────────────────────────────────────┘
                         │
                         ▼
┌─ STEP 8: Tool Node ─────────────────────────────────────────┐
│ Output: [                                                    │
│   ('Making Pasta from Scratch', 'Bon Appetit',               │
│    '2023-03-15', 4200000),                                   │
│   ('Best Air Fryer Recipes 2023', 'Tasty',                   │
│    '2023-08-22', 1800000),                                   │
│ ]                                                            │
└──────────────────────────────────────────────────────────────┘
                         │
                         ▼
┌─ STEP 9: Agent Node (Final Answer) ─────────────────────────┐
│                                                              │
│ "Based on your history, I found 2 cooking-related videos     │
│  you watched in 2023:                                        │
│                                                              │
│  1. **Making Pasta from Scratch** by Bon Appetit             │
│     (March 15, 2023) — 4.2M views                            │
│  2. **| **LangGraph ReAct Agent** ✅ | LLM reasons, acts, observes, repeats until done | Handles all question types. Dynamically combines tools. Self-corrects on errors. No fixed path — the execution trace is as long or short as the question demands. |

        ← Tool result
messages[10] = AIMessage(content="Based on your...")    ← Final answer (no tool_calls)
```

The agent terminates when the LLM produces an `AIMessage` with `content` but no `tool_calls`. The final message (`messages[-1].content`) is what gets returned to Flutter as the response.

**Why this matters:** Every Thought, Action, and Observation is preserved in the message list. If you needed to debug why the agent gave a wrong answer, you could inspect `result["messages"]` to see exactly what SQL it wrote, what the database returned, and how the LLM interpreted it. This transparency is impossible with black-box chain architectures.

#### 4.5.8 Error Self-Correction in Practice

When the agent writes bad SQL (and it will — no LLM is perfect), the error becomes an Observation that the LLM can learn from:

```
Step 1: LLM writes:  SELECT titles FROM youtube_history LIMIT 5
Step 2: Tool returns: ERROR: column "titles" does not exist.
                      Hint: Perhaps you meant "video_title".
Step 3: LLM reasons: The column is called video_title, not titles.
                      Let me fix that.
Step 4: LLM writes:  SELECT video_title FROM youtube_history LIMIT 5
Step 5: Tool returns: [('Python Tutorial', ...), ...]
Step 6: LLM answers: Here are 5 videos from your history...
```

This self-correction loop is **why Rule 1 (always inspect schema first) exists**. If the agent checks `sql_db_schema` before writing SQL, it gets the correct column names upfront and avoids the error-retry cycle entirely. The rule is a performance optimization — it prevents wasted LLM calls and database round-trips.

#### 4.5.9 Why Not Alternatives? — Detailed Comparison

| Architecture | How It Works | Why It Fails For Our Use Case |
|-------------|-------------|-------------------------------|
| **Naive RAG Chain** (embed → retrieve → generate) | Embeds the user question, retrieves top-K similar documents from a vector store, feeds them to the LLM | Cannot answer "how many videos did I watch?" — this requires SQL aggregation (`COUNT(*)`), not document retrieval. The chain has no concept of structured queries. |
| **SQL-only Agent** (text-to-SQL) | Converts natural language directly to SQL | Cannot answer "find videos about cooking" — SQL `LIKE` patterns miss semantically similar results. There's no vector search capability. |
| **Multi-Chain Router** (classify → route to chain A or B) | A classifier LLM first categorizes the question type, then routes to the appropriate chain | Fails on **combined queries** like "What cooking videos did I watch in 2023?" — this needs both semantic search AND SQL in sequence. A router picks one chain, not a combination. Also adds latency (extra LLM call for classification). |
| **Function Calling (OpenAI-style)** | LLM generates structured function calls in a single turn | Can only call tools *once per turn*. Our "cooking videos in 2023" example requires 4 sequential tool calls where each call's output informs the next. Single-turn function calling can't do multi-step reasoning. |
| **LangGraph ReAct Agent** ✅ | LLM reasons, acts, observes, repeats until done | Handles all question types. Dynamically combines tools. Self-corrects on errors. No fixed path — the execution trace is as long or short as the question demands. |

training needed — critical for our taxonomy drift feature where categories are added at runtime.

**Why ef_construction=256?**
The `interest_categories` table is small (30-50 rows), but classification accuracy is critical — every raw log is classified by finding its nearest category embedding. With `ef_construction=256` (vs. the default 64), the HNSW graph is built with 4× more candidate neighbors during construction, producing near-perfect recall. The build time penalty is negligible on a 50-row table.

```
User Question → LLM Reasons → Selects Tool → Executes Tool → LLM Interprets Result → Answer
```

The agent has access to these tools:

| Tool | Purpose | When Used |
|------|---------|-----------|
| `sql_db_list_tables` | List available tables | Agent inspects schema before writing SQL |
| `sql_db_schema` | Get table columns/types | Agent learns column names |
| `sql_db_query` | Execute SELECT queries | Exact counts, dates, specific lookups |
| `semantic_youtube_search` | pgvector cosine similarity search | "Find videos about X", conceptual queries |
| `generate_longitudinal_report` | Monthly category matrix + yearly highlights | "How have my interests evolved?" |

**Why not a simple chain?** A chain follows a fixed path (embed → retrieve → generate). But our questions require different tools:
- "How many videos did I watch?" → SQL only
- "Find videos about cooking" → Semantic search only
- "How have my interests changed over time?" → Longitudinal report tool
- "What cooking videos did I watch in 2023?" → SQL + semantic search combined

The ReAct agent dynamically decides which tools to invoke, in what order, and how to combine their results. This flexibility is impossible with a fixed retrieval chain.

### 4.6 Why YouTube API Enrichment?

Google Takeout CSVs contain only URLs and timestamps — no video titles, channels, or categories. The YouTube Data API v3 enriches each record with:

- `video_title`, `video_description`
- `channel_title`
- `category_id`, `category_name`
- `view_count`, `like_count`

**Without enrichment**, semantic search would operate on raw URLs (useless). **With enrichment**, the embedding of `"Python Tutorial for Beginners (Channel: Corey Schafer)"` captures the actual meaning.

**Quota handling:** The YouTube API has a daily quota of ~10,000 units. Our enrichment uses `videos.list` (1 unit per request, 50 videos per batch). We detect `quotaExceeded` errors immediately (fail-fast) rather than sleeping through retry loops, and gracefully save whatever was already enriched.

### 4.7 The Classification System — Nearest-Category Matching

After embedding, every raw log is classified against a predefined **interest taxonomy**:

```
Software Engineering
├── Machine Learning & AI
├── Frontend & UI Development
├── Backend Architecture
├── Mobile App Development
├── DevOps & Deployment
├── Python Programming
└── Database Optimization

Productivity & Optimization
├── Time Management
├── Note Taking & Zettelkasten
├── Focus & Deep Work
└── Workflow Automation

(... 6 parent categories, ~28 subcategories total)
```

Each category name is embedded into a 384-dim vector and stored in `interest_categories`. Classification is performed entirely **inside PostgreSQL** using a `CROSS JOIN LATERAL` query:

```sql
SELECT y.id, ic.id, (1 - (y.embedding <=> ic.embedding)) AS confidence_score
FROM youtube_history y
CROSS JOIN LATERAL (
    SELECT id, embedding FROM interest_categories
    ORDER BY embedding <=> y.embedding LIMIT 1
) ic;
```

**Why in-database?** Moving vectors out of the DB, computing distances in Python, and writing back would be catastrophically slow for thousands of records. The `CROSS JOIN LATERAL` approach uses the HNSW index to find the nearest category in O(log n) per record, running the entire classification in seconds.

---

## 5. Frontend: Design Decisions & Rationale

### 5.1 Why Flutter Desktop?

| Factor | Flutter | Electron | Native WinUI |
|--------|---------|----------|------------|
| **Cross-platform** | Windows, macOS, Linux, iOS, Android from one codebase | Windows, macOS, Linux only | Windows only |
| **Performance** | Compiled to native ARM/x86 | Chromium runtime (~200MB overhead) | Native |
| **UI quality** | Material 3 with full customization | Web-based | Native Windows look |
| **Future mobile** | Zero code changes needed | Impossible | Impossible |

Flutter was chosen specifically because the same codebase can later run on Android/iOS with zero modifications. The `http` package, `path_provider`, `file_picker`, and `flutter_markdown` all work identically across platforms.

### 5.2 The Connection Dialog — Why URL Parsing?

When you paste a Supabase connection string:
```
postgresql://postgres.lqxvoarityebqongdiru:password@aws-0-region.pooler.supabase.com:6543/postgres
```

The Flutter app automatically extracts:
- **Project Ref**: `lqxvoarityebqongdiru`
- **Host**: `aws-0-region.pooler.supabase.com`
- **Port**: `6543`

**Why?** Supabase's dashboard shows the full connection string, but the backend API expects individual fields (for URL-safe password encoding). Rather than making the user manually split the string, we parse it with regex. The raw password is requested separately because connection strings contain URL-encoded passwords (e.g., `%24` instead of `$`), and we need the original password for proper encoding.

### 5.3 The DeepSeek API Key Field

The connection dialog also requests a **DeepSeek API Key**. This key is sent to the backend, which uses it to:
1. Initialize the `ChatOpenAI` LLM client (for the ReAct agent)
2. Power taxonomy drift analysis (LLM clustering of unclassified logs)

**Why not hardcoded?** Each user should control their own API key and billing. The key is never stored persistently — it lives only in the backend's `DBState` object for the duration of the session.

---

## 6. The Ingestion Pipeline — Step by Step

When you upload a CSV or HTML file, the following pipeline executes:

```
┌───────────────────────────────────────────────────────────────┐
│ PHASE 1: UPLOAD & ENRICHMENT (Synchronous — Immediate)       │
│                                                               │
│  1. File parsed (CSV or HTML via BeautifulSoup)               │
│  2. Service type detected (YouTube or Search)                 │
│  3. YouTube: Video IDs extracted, enriched via YouTube API    │
│     Search: Google redirect URLs resolved to actual domains   │
│  4. Enriched data stored in Supabase tables                   │
│  5. Response returned to Flutter with row counts              │
│                                                               │
│ PHASE 2: INDEXING PIPELINE (Background — Async)               │
│                                                               │
│  6. BGE-small embeddings generated for all new records        │
│  7. Vectors saved to embedding columns in Supabase            │
│  8. Nearest-category classification via CROSS JOIN LATERAL    │
│  9. Classification results stored in log_classifications      │
│ 10. Frontend notified via /status polling ("Ready")           │
└───────────────────────────────────────────────────────────────┘
```

**Why two phases?** Phase 1 (enrichment + storage) takes seconds. Phase 2 (embedding + classification) can take minutes for large datasets. Running Phase 2 in a `BackgroundTasks` thread lets the user continue chatting immediately. The Flutter UI polls `/status` every 2 seconds and shows a real-time progress banner.

---

## 7. The RAG Query Engine — How Questions Are Answered

```
User: "What cooking videos did I watch in 2023?"
                    │
                    ▼
           ┌─────────────┐
           │  LangGraph   │
           │  ReAct Agent │
           └──────┬──────┘
                  │
    ┌─────────────┼─────────────┐
    │             │             │
    ▼             ▼             ▼
┌────────┐  ┌──────────┐  ┌──────────────┐
│ Schema │  │ Semantic  │  │ SQL Query    │
│ Tool   │  │ Search    │  │ Tool         │
│ (once) │  │ "cooking" │  │ WHERE year=  │
└────────┘  └──────────┘  │  2023        │
                          └──────────────┘
                    │
                    ▼
           ┌─────────────┐
           │  LLM merges  │
           │  results     │
           │  into answer │
           └─────────────┘
```

The `generate_longitudinal_report` tool deserves special attention. When triggered, it:

1. Builds a **monthly statistical matrix** — for every month in the user's history, it counts interactions per interest category
2. Extracts **yearly highlights** — for each year, identifies the dominant category and fetches 2 representative logs as evidence
3. Returns a compressed JSON package to the LLM, which synthesizes it into a narrative report

**Why only 2 representative logs per year?** LLM context windows are limited. Sending all logs would exceed token limits and degrade output quality. Two high-confidence examples per year give the LLM enough grounding to write an accurate narrative without overwhelming it.

---

## 8. Taxonomy Drift — The Self-Evolving Interest Model

### 8.1 The Problem

A fixed taxonomy becomes stale. If the predefined categories cover "Software Engineering" and "Gaming" but the user starts watching woodworking videos, those logs get classified with low confidence scores — they don't match any existing category well.

### 8.2 The Solution: Drift Detection & Resolution

The **Drift Analysis** button (🧠 icon in the app bar) triggers a three-stage process:

**Stage 1 — Detection:**
```sql
-- Find logs classified with low confidence
SELECT * FROM log_classifications lc
JOIN youtube_history yh ON lc.youtube_log_id = yh.id
WHERE lc.confidence_score < 0.55
  AND yh.drift_attempts < 2    -- Only logs not already retried twice
```

**Stage 2 — LLM Clustering:**
The low-confidence log texts are sent to DeepSeek with this prompt:
> "Cluster these digital activity logs and suggest 1-3 new category names."

The LLM returns something like: `["Woodworking & DIY", "Home Renovation"]`

**Stage 3 — User Approval & Application:**
The Flutter UI shows the suggested categories in a selectable dialog. The user can approve, modify, or reject them. On approval:
1. New categories are embedded and inserted into `interest_categories`
2. Low-confidence classifications are **wiped** from `log_classifications`
3. `drift_attempts` is incremented on the raw logs (prevents infinite retry loops)
4. Background re-classification runs with the expanded taxonomy

### 8.3 The Drift Attempt Counter — Preventing Infinite Loops

Some logs are inherently unclassifiable — erratic URLs, tracking parameters, junk strings. Without a guard, the system would endlessly retry classifying them, each time getting low confidence, each time triggering drift analysis.

The `drift_attempts INT DEFAULT 0` column on `youtube_history` and `search_history` acts as a circuit breaker:
- Attempt 0 → first classification
- Attempt 1 → drift detected, new categories added, re-classified
- Attempt 2 → **permanently excluded** from future drift scans

This guarantees convergence: the drift system will never loop more than twice on any log.

### 8.4 Confidence Thresholds

| Data Source | Threshold | Rationale |
|------------|-----------|-----------|
| YouTube | 0.55 | Video titles are semantically rich ("Python Tutorial for Beginners"), so higher confidence is expected for correct matches |
| Search | 0.45 | Search queries are often terse domain names ("stackoverflow.com"), so lower confidence is acceptable |

---

## 9. Chat History Persistence — Local Storage Architecture

### 9.1 The Problem

Without persistence, every app restart loses all conversation history. Users lose context, can't reference previous analyses, and the experience feels disposable.

### 9.2 Design Decision: JSON Document Store vs. SQLite

| Factor | JSON File | SQLite (sqflite_common_ffi) |
|--------|-----------|----------------------------|
| **Windows build reliability** | 100% — pure Dart, no native code | Requires C compiler, SQLite FFI bindings, and platform-specific setup |
| **Performance (1000 messages)** | ~2ms read/write | ~1ms read/write |
| **Complexity** | Zero configuration | Needs `sqflite_common_ffi`, `sqlite3_flutter_libs`, Windows-specific initialization |
| **Cross-platform** | Works everywhere with zero changes | Different packages needed per platform |
| **Data model fit** | Chat sessions are hierarchical (Session → Messages) — perfect for JSON | Requires normalized tables with joins |

**Verdict:** The marginal speed advantage of SQLite (~1ms vs ~2ms) is irrelevant for chat history. The build reliability advantage of pure Dart JSON is decisive. A JSON document store eliminates the single most common Flutter Windows build failure — native FFI compilation errors.

### 9.3 Storage Location & Cross-Device Behavior

The `path_provider` package resolves the application documents directory per platform:

| Platform | Path | Survives App Restart? | Survives OS Reboot? |
|----------|------|----------------------|---------------------|
| Windows | `C:\Users\{user}\Documents\chat_sessions.json` | ✅ Yes | ✅ Yes |
| Android | `/data/data/com.example.app/files/chat_sessions.json` | ✅ Yes | ✅ Yes |
| iOS | `~/Library/Application Support/chat_sessions.json` | ✅ Yes | ✅ Yes |
| macOS | `~/Library/Application Support/chat_sessions.json` | ✅ Yes | ✅ Yes |

**Critical note:** Chat history is **local to each device**. Running the app on Windows and then on Android will show separate, independent chat histories. This is by design — it matches the behavior of every local-first application (Signal, Obsidian, VS Code settings).

### 9.4 Data Model

```dart
class ChatMessage {
  final String text;
  final bool isUser;
  final DateTime timestamp;
  // + toJson() / fromJson() serialization
}

class ChatSession {
  final String id;           // Microsecond epoch (unique per session)
  final String title;        // Auto-generated from first user message
  final DateTime lastActive; // Updated on every message
  final List<ChatMessage> messages;
  // + toJson() / fromJson() serialization
}
```

### 9.5 Auto-Title Generation

When a new chat session is created, it's titled "New Chat". The moment the user sends their first message, the title is automatically updated to the first 26 characters of that message:

```
"What cooking videos did I wa..." → Session title
```

This mimics the behavior of ChatGPT, Claude, and other premium AI chat interfaces — the user never needs to manually name their conversations.

### 9.6 Auto-Save Strategy

Every message — whether sent by the user or received from the AI — triggers `_saveSessionsToStorage()`. This means:
- Crash recovery: even if the app crashes mid-conversation, all messages up to the last one are preserved
- No explicit "save" button needed
- The save operation is lightweight (~2ms for a typical session) and non-blocking

### 9.7 Multi-Session Navigation Drawer

The sidebar drawer provides a ChatGPT-like interface for managing multiple conversations:

- **"+ New Chat"** button with gradient styling creates a fresh session
- **Session list** shows all historical threads, sorted by `lastActive` (most recent first)
- **Active session** is visually highlighted with a border and accent color
- **Delete** buttons on each session remove it from storage immediately
- **Footer** shows "Local Document Database" as a status indicator

---

## 10. User Manual: Getting Started

### 10.1 Prerequisites

| Component | Version | Purpose |
|-----------|---------|---------|
| Python | 3.10+ | Backend runtime |
| Flutter | 3.x | Frontend framework |
| Supabase account | Free tier | Managed PostgreSQL + pgvector |
| DeepSeek API key | — | LLM for RAG agent + drift analysis |
| YouTube API key | — | Video metadata enrichment (optional for Search-only) |

### 10.2 Step 1: Set Up Supabase

1. Create a free project at [supabase.com](https://supabase.com)
2. Note your **Database Password** (set during project creation)
3. Click **Connect** → **Transaction Pooler** and copy the connection string
4. Open the **SQL Editor** and run the schema setup (see `SUPABASE_SETUP.md`)

### 10.3 Step 2: Start the Backend

```bash
cd D:\GOOGLE_TAKEOUT_RAG
pip install -r requirements.txt

# Also install the LangChain/ML stack:
pip install langchain langchain-openai langchain-community langchain-huggingface
pip install langgraph sqlalchemy psycopg2-binary sentence-transformers

python app.py
```

Or simply double-click `start_api.bat`.

The server starts at `http://localhost:8000`. The BGE embedding model downloads automatically on first run (~130MB).

### 10.4 Step 3: Launch the Flutter App

```bash
cd D:\GOOGLE_TAKEOUT_RAG\frontend\flutter_application
flutter pub get
flutter run -d windows
```

### 10.5 Step 4: Connect to Supabase (First Screen)

When the app launches, a connection dialog appears:

1. **Connection URL** — Paste your Supabase connection string
2. **Raw Database Password** — Enter the password you set during project creation
3. **DeepSeek API Key** — Enter your API key from [platform.deepseek.com](https://platform.deepseek.com)

Click **"Connect & Initialize"**. The backend will:
- Verify the database connection
- Auto-create any missing tables (`interest_categories`, `log_classifications`)
- Seed the default interest taxonomy (28 categories)
- Initialize the LangGraph agent

### 10.6 Step 5: Upload Your Data

1. Click the **upload icon** (📤) in the app bar
2. Enter your **YouTube API Key** (optional — required only for YouTube data enrichment)
3. Click **"Pick File & Upload"** and select your Google Takeout CSV or HTML file
4. Wait for the enrichment phase to complete (~10-30 seconds depending on file size)
5. The background indexing banner appears — embeddings and classifications are being generated
6. Once the banner disappears and you see "🎉 Ingestion & Indexing pipeline completed successfully!", you're ready to chat

### 10.7 Step 6: Ask Questions

Type your question in the input field and press Enter or click Send:

- **Exact queries**: "How many YouTube videos did I watch in 2024?" → SQL
- **Semantic queries**: "Find videos about machine learning" → Vector search
- **Evolution reports**: "How have my interests changed over the years?" → Longitudinal report
- **Combined**: "Which AI channels did I watch most in 2023?" → SQL + semantic

### 10.8 Step 7: Review Taxonomy Drift (Optional)

Click the **brain icon** (🧠) in the app bar to scan for unclassified activity. If new interest patterns are detected, the system suggests new categories. Approve them to expand your personal taxonomy.

---

## 11. API Reference

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `POST` | `/connect-db` | Initialize database connection and LangGraph agent |
| `POST` | `/chat` | Send a natural-language query to the RAG agent |
| `POST` | `/upload-and-process-csv` | Upload and process a CSV/HTML file with enrichment + indexing |
| `POST` | `/process-csv/` | Legacy endpoint — process CSV and return as download (backward-compatible) |
| `GET` | `/status` | Get indexing status, API version, feature flags |
| `GET` | `/drift-analysis` | Scan for low-confidence classifications and suggest new categories |
| `POST` | `/apply-drift` | Apply approved drift categories and trigger re-classification |
| `GET` | `/` | Health check and endpoint listing |

### 11.1 POST /connect-db

**Request Body:**
```json
{
  "db_project_ref": "lqxvoarityebqongdiru",
  "db_password": "your-password",
  "db_host": "aws-0-region.pooler.supabase.com",
  "db_port": "6543",
  "llm_api_key": "sk-..."
}
```

**Response:**
```json
{
  "status": "success",
  "message": "Connected to database and initialized agent."
}
```

### 11.2 POST /chat

**Request Body:**
```json
{
  "query": "What was my most watched YouTube category in 2023?"
}
```

**Response:**
```json
{
  "response": "Based on your data, your most watched category in 2023 was..."
}
```

### 11.3 GET /status

**Response:**
```json
{
  "api_version": "1.2",
  "database_connected": true,
  "is_indexing": false,
  "indexing_message": "Ready",
  "features": {
    "chat_with_agent": true,
    "csv_processing": true,
    "semantic_search": true,
    "sql_tools": true
  }
}
```

---

## 12. Troubleshooting

### Backend Won't Start

```bash
# Check if port 8000 is in use
netstat -ano | findstr :8000

# Try a different port
python -c "import uvicorn; uvicorn.run('app:app', host='0.0.0.0', port=8001)"
```

### YouTube API Quota Exceeded

The system gracefully handles quota exhaustion. It saves all already-enriched records and returns a warning with the count of successfully processed rows. Wait 24 hours for quota reset, then re-upload only the unenriched remainder.

### Database Connection Timeout

If `ALTER TABLE` or migration statements hang, a stale transaction may be blocking the lock. Check `pg_stat_activity` in Supabase SQL Editor:

```sql
SELECT pid, state, query, age(clock_timestamp(), xact_start) AS duration
FROM pg_stat_activity
WHERE state = 'idle in transaction'
ORDER BY duration DESC;
```

Terminate blocking processes with `SELECT pg_terminate_backend(<pid>);`

### Flutter App Can't Connect to Backend

Ensure the FastAPI server is running on `http://127.0.0.1:8000`. The Flutter app on Windows uses `127.0.0.1`. If running on Android emulator, the app automatically switches to `10.0.2.2:8000` (Android's alias for the host machine's localhost).

### Chat History Not Persisting

Verify that `path_provider` is correctly resolving the documents directory:
```dart
final dir = await getApplicationDocumentsDirectory();
print(dir.path);  // Should print: C:\Users\{user}\Documents
```

The `chat_sessions.json` file should exist at this path after the first conversation.

---

## 13. File Map & Architecture Diagram

```
D:\GOOGLE_TAKEOUT_RAG\
│
├── app.py                    # FastAPI backend: all endpoints, RAG agent, ingestion pipeline
├── db_config.py              # Database credential management & connection validation
├── parse_takeout.py          # HTML parser for Google Takeout "My Activity" format
├── youtube_csv_enrich.py     # YouTube API enrichment (standalone CLI version)
├── classify_logs.py          # Log classification engine (standalone CLI version)
├── generate_embeddings.py    # BGE embedding generator (standalone CLI version)
├── seed_categories.py        # Taxonomy seeder (standalone CLI version)
├── run_drift_analysis.py     # Drift analysis engine (standalone CLI version)
├── run_migration.py          # Database schema migration runner (direct psycopg2)
├── phase1_schema_update.sql  # SQL migration: drift_attempts column + HNSW index tuning
├── client.py                 # Python test client for API endpoints
├── example_usage.py          # Example usage script
├── generate_test_data.py     # Test data generator
├── requirements.txt          # Python dependencies
├── start_api.bat             # One-click Windows server launcher
├── SUPABASE_SETUP.md         # Step-by-step Supabase configuration guide
├── README.md                 # This document
│
└── frontend/
    └── flutter_application/
        ├── lib/
        │   └── main.dart     # Complete Flutter app: UI, state, chat history, API client
        └── pubspec.yaml      # Flutter dependencies (path_provider, http, file_picker, etc.)
```

### Database Schema

```
┌──────────────────────────┐     ┌──────────────────────────┐
│    youtube_history       │     │    search_history        │
├──────────────────────────┤     ├──────────────────────────┤
│ id (SERIAL PK)           │     │ id (SERIAL PK)           │
│ service (TEXT)            │     │ service (TEXT)            │
│ action (TEXT)             │     │ action (TEXT)             │
│ timestamp (TIMESTAMP)    │     │ timestamp (TIMESTAMP)    │
│ links (TEXT)              │     │ links (TEXT)              │
│ video_id (TEXT)           │     │ actual_website (TEXT)    │
│ video_title (TEXT)        │     │ embedding (VECTOR 384)   │
│ video_description (TEXT)  │     │ drift_attempts (INT)     │
│ channel_title (TEXT)      │     └──────────┬───────────────┘
│ category_id (BIGINT)     │                 │
│ category_name (TEXT)      │                 │
│ view_count (BIGINT)       │                 │
│ like_count (BIGINT)       │                 │
│ embedding (VECTOR 384)   │                 │
│ drift_attempts (INT)     │                 │
└──────────┬───────────────┘                 │
           │                                 │
           │   ┌──────────────────────────┐  │
           │   │  log_classifications     │  │
           │   ├──────────────────────────┤  │
           ├──►│ id (SERIAL PK)           │◄─┤
           │   │ youtube_log_id (FK)      │  │
           │   │ search_log_id (FK)       │  │
           │   │ category_id (FK) ────────┼──┼──┐
           │   │ confidence_score (FLOAT) │  │  │
           │   └──────────────────────────┘  │  │
           │                                 │  │
           │   ┌──────────────────────────┐  │  │
           │   │  interest_categories     │  │  │
           │   ├──────────────────────────┤  │  │
           │   │ id (SERIAL PK)      ◄────┼──┼──┘
           │   │ category_name (TEXT)     │  │
           │   │ embedding (VECTOR 384)  │  │
           │   │ is_global (BOOL)        │  │
           │   │ parent_id (INT, nullable)│  │
           │   │ HNSW INDEX (ef=256)     │  │
           │   └──────────────────────────┘  │
           │                                 │
           └─────────────────────────────────┘
```

---

## License

This project is provided as-is for personal and educational use.
