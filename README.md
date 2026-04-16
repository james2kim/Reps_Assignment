# BigSpring Reps — Knowledge-to-Action Search Engine

A secure, multi-tenant generative search engine that allows sales representatives to search their assigned training materials and personal practice history with strict authorization scoping.

## Quick Start

### Prerequisites

- **Python 3.11+**
- **Docker Desktop** (for Postgres)
- **Node.js 18+** (for frontend)
- **Anthropic API key** (for LLM-powered answers)

### Setup (3 commands)

```bash
# 1. Install Python dependencies
pip3 install -e ".[dev]"

# 2. Configure API key
cp .env .env.local  # then edit .env and add your ANTHROPIC_API_KEY

# 3. Initialize database (starts Postgres, creates tables, seeds data, builds chunks, generates embeddings)
bash scripts/init_db.sh
```

### Run

```bash
# Backend (port 8000)
python3 -m uvicorn backend.app.main:app --reload --port 8000

# Frontend (port 3000) — in a separate terminal
cd frontend && npm install && npm run dev
```

Open **http://localhost:3000** — select a company, select a user, search.

### Test

```bash
# Unit + integration tests (no API key needed, ~25s)
pytest backend/app/tests/ --ignore=backend/app/tests/test_evaluations.py

# Full evaluation suite with LLM (requires API key, ~80s)
pytest backend/app/tests/test_evaluations.py -v
```

---

## Architecture

### Pattern: Router with Stratified Retrieval

We use a **Router Pattern** where a classifier determines the query intent and retrieval strategy, then dispatches to specialized backends.

```
User Query
    |
    v
[Scope Resolver] ──> SearchScope (allowed IDs)
    |
    v
[Query Classifier] ──> Intent + Strategy
    |
    ├── out_of_scope ──────────> Static guardrail response
    ├── general_professional ──> LLM general knowledge + disclaimer
    ├── proprietary_ungrounded > Static guardrail response
    └── assigned_search ───────> Retrieval Strategy:
         |
         ├── structured ──> SQL lookup (scores, plays, statuses)
         ├── document ────> Chunk retrieval pipeline → LLM grounded answer
         └── hybrid ──────> Both structured + document
                               |
                               v
                    [Relevance Filter → Token Budget → LLM Context]
                               |
                               v
                    [Answer Generator] ──> Streaming response + citations
```

### Why Router Pattern?

- **Predictable**: Classification is explicit and testable (140 tests prove it)
- **Auditable**: Thought trace shows exactly why each query was routed where
- **Efficient**: Out-of-scope queries never touch the database; structured queries skip RAG
- **Extensible**: New intents/strategies can be added without modifying existing paths

### Key Design Decisions

**Authorization before retrieval**: The `ScopeResolver` runs FIRST and produces a deterministic set of allowed IDs. The SQL WHERE clause in chunk retrieval is parameterized by these IDs — there is no post-hoc filtering. This guarantees no data leakage even if the LLM or ranking logic has bugs.

**Structured vs Document retrieval**: Not everything is RAG. "What was my score?" is a SQL query against the `feedback` table. "What is Hexenon?" requires document chunks. "How can I improve based on my feedback?" needs both. The classifier determines which path to take.

**LLM-first classification for ambiguous queries**: Rule-based keyword matching handles high-confidence cases (product names, structured keywords). Everything else goes to the LLM classifier with the user's play titles as context, so it can determine if "What is the eradication rate for Streptococcus pneumoniae?" relates to the user's Amproxin training.

**Citation filtering**: Citations are built from retrieved chunks but filtered to only those the LLM actually referenced in its answer. This prevents showing irrelevant sources when the LLM ignores low-relevance chunks.

---

## Core Components

### 1. Scope Resolver (`core/scope_resolver.py`)

Resolves the complete authorization boundary for a user:

```
user → play_assignments → plays → reps (watch only) → assets
user → submissions → feedback
```

Returns a `SearchScope` containing: `allowed_play_ids`, `allowed_rep_ids`, `allowed_asset_ids`, `allowed_submission_ids`, `allowed_feedback_ids`, `play_titles`.

### 2. Query Classifier (`core/query_classifier.py`)

Two-layer classification:

| Layer | Handles | Speed |
|---|---|---|
| Rules | Product keywords, structured keywords, history keywords | <1ms |
| LLM | Everything else (greetings, general knowledge, ambiguous) | ~500ms |

Outputs both **intent** (what the query is about) and **strategy** (how to answer it).

### 3. Retrieval Pipeline (`core/retrieval_router.py`)

For document retrieval, the pipeline is:

1. **Scope filter** — SQL WHERE clause limits to allowed asset/submission IDs
2. **Hybrid ranking** — combines three signals:
   - **Vector cosine similarity** (pgvector) — semantic matching via sentence-transformers embeddings (384d, all-MiniLM-L6-v2)
   - **Full-text search** (ts_rank_cd) — word matching with stemming
   - **Trigram similarity** (pg_trgm) — fuzzy/typo matching
   - Combined: `vec_score * 3 + ts_score * 2 + trgm_score * 1`
3. **Top-K candidates** — retrieve 15 candidates
4. **Relevance threshold** — drop chunks below absolute score AND below 20% of top score
5. **Token budget** — trim to 3000 tokens / 5 chunks max
6. **Context labeling** — chunks labeled as TRAINING MATERIALS or USER HISTORY

Falls back to text-only ranking if embeddings are not yet generated.

**Chunking strategy**: Paragraph-level chunks optimized for embedding quality:

| Asset type | Strategy | Avg size |
|---|---|---|
| PDF | One chunk per page (sections + tables merged into rich context) + separate table chunks | ~630 chars |
| Video/Audio | Full transcript + grouped segments (4 per paragraph) | ~330 chars |
| Image | Single chunk (alt_text + ocr_text) | ~340 chars |
| Text | Single chunk (submission text) | ~350 chars |
| Feedback | Single chunk per feedback entry | ~90 chars |

### 4. Answer Generator (`core/answer_generator.py`)

| Intent | Action |
|---|---|
| `out_of_scope` | Static: "I am a specialized search engine for your assigned Reps materials..." |
| `general_professional` | LLM general answer + disclaimer |
| `proprietary_ungrounded` | Static: "I cannot find any specific information..." |
| `assigned_search` | LLM grounded answer from retrieved context + citations |

Supports both sync (`generate_answer`) and streaming (`generate_answer_stream`) modes.

### 5. Guardrails (`core/guardrails.py`)

Three-tier guardrail system matching the spec exactly:

1. **Search Boundary**: Out-of-scope queries get blocked with no retrieval
2. **General Professional Fallback**: Sales technique questions answered from LLM knowledge with explicit disclaimer
3. **Proprietary Data Guard**: Product queries without grounding get a "cannot find" response — no hallucination

Additional guards:
- LLM prompt instructs verbatim "not found" response (no query details leaked)
- Citation filter suppresses sources when answer is "not found"
- Context labeling prevents the LLM from revealing what IS in the materials

### 6. Citations (`core/citations.py`)

Deep-linked citations by asset type:

| Type | Format |
|---|---|
| PDF | `[PDF: amproxin_guide.pdf, Page 1]` |
| Video | `[Video: synthetic_sinew_demo.mp4, 00:26 - 00:38]` |
| Audio | `[Audio: kyb_user_sub_1.mp3, 00:26 - 00:38]` |
| Image | `[Image: neuro_linker_diagram.png]` |
| Feedback | `[Feedback: score 8/10]` |

---

## Database

### Schema

Postgres 16 with 9 tables, TEXT primary keys matching source CSV IDs:

| Table | Rows | Description |
|---|---|---|
| companies | 5 | Veldra, Aetheris, Kyberon, Sentivue, Hexaloom |
| users | 224 | Sales representatives |
| plays | 15 | Training play sequences |
| play_assignments | 82 | User ↔ play mappings (authorization) |
| assets | 63 | Content manifests |
| reps | 37 | Watch/practice tasks within plays |
| submissions | 38 | User practice responses |
| feedback | 38 | AI coaching scores + text |
| search_chunks | 187 | RAG-ready chunks with 384d vector embeddings (83 training + 66 submissions + 38 feedback) |

### Data Notes

Source CSVs contain orphan FK references (user `j0i9-305`, plays `hex-006..010`, rep `hex-024`). The seed script logs warnings and skips 20 rows total. This is a data issue, not a code issue.

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Health check |
| GET | `/companies` | List all companies |
| GET | `/companies/{id}/users` | List users for a company |
| POST | `/search` | Synchronous search (full response) |
| POST | `/search/stream` | SSE streaming (token-by-token) |

### SSE Stream Events

```
data: {"type": "trace", "intent": "assigned_search", "strategy": "document", ...}
data: {"type": "token", "text": "The eradication rate..."}
data: {"type": "token", "text": " is 94.2%..."}
data: {"type": "citation", "label": "[PDF: amproxin_guide.pdf, Page 1]", ...}
data: {"type": "done"}
```

---

## Frontend

React + Vite single-page app with:

- **Company/User selectors** — cascading dropdowns
- **Search bar** — natural language input
- **Streaming answer** — tokens appear incrementally with cursor
- **Collapsible thought trace** — shows intent, strategy, confidence, reason
- **Color-coded citation chips** — PDF (red), Video (blue), Audio (green), Feedback (amber)
- **Disclaimer banner** — for general professional responses

---

## Testing

### 140 tests across 7 test files

| File | Tests | What it covers |
|---|---|---|
| `test_scope_resolver.py` | 18 | Authorization chains, cross-company, peer isolation |
| `test_query_classifier.py` | 13 | Rule-based + LLM intent classification |
| `test_retrieval.py` | 24 | Chunk retrieval, scope filtering, Precision@K, MRR |
| `test_router.py` | 9 | Structured/document/hybrid dispatch |
| `test_answer_generator.py` | 13 | Guardrails, citations, thought trace |
| `test_spec_cases.py` | 28 | Spec test cases adapted to actual seed data |
| `test_evaluations.py` | 30 | Full E2E eval with LLM (all spec scenarios) |

### Retrieval Quality Metrics

**Precision@3**: For each ground-truth query, at least 1 of the top 3 results comes from the correct asset.

**Mean Reciprocal Rank (MRR)**: Across 4 users and 16 queries, the first relevant result appears in the top 2 on average (MRR >= 0.5).

### Evaluation Framework (`test_evaluations.py`)

Maps every spec test case to automated assertions:

| Case | Scenario | Checks |
|---|---|---|
| 1.1 | Aaron + Amproxin eradication rate | Answer contains 94.2%, cites amproxin_guide.pdf |
| 1.2 | Daphne + cooling costs timestamp | Answer contains 32%, 00:26, audio citation |
| 2.1 | Sophie + cross-company GridMaster | No Kyberon content, no citations, no context leak |
| 2.2 | Leo + unassigned Nuvia play | Scope excludes play-aet-002, answer is not-found |
| 2.3 | Aaron + peer submission search | Cannot see other users' transcripts |
| 3.1 | Belinda + Lydrenex disambiguation | Sees Zaloric (50-100mg), not Nuvia (5-10mg) |
| 3.2 | Daphne + multi-page rack temperature | 24.5C baseline, 21.8C result, 11% gain |
| 4.1 | Clark + "Sentalink" typo | Fuzzy matches to Sentilink, finds 15x figure |
| 4.2 | Quinn + chocolate cake | Out-of-scope guardrail, no LLM knowledge leaked |

---

## Project Structure

```
backend/app/
  api/
    routes/         # FastAPI endpoints (search, companies, users, health)
    schemas/        # Pydantic request/response models
  core/
    scope_resolver.py     # Authorization — resolves allowed IDs
    query_classifier.py   # Intent + strategy classification (rules + LLM)
    retrieval_router.py   # Dispatches to structured/document/hybrid
    answer_generator.py   # LLM grounded answers + streaming
    citations.py          # Citation building + dedup + filtering
    guardrails.py         # Exact guardrail response text
  db/
    schema.sql            # Postgres DDL
    session.py            # SQLAlchemy engine + session
    models/               # ORM models (9 tables)
  ingestion/
    seed_relational_data.py  # CSV/JSON → Postgres
    parse_assets.py          # Asset JSON parsers (PDF, video, audio, image, text)
    build_chunks.py          # Builds search_chunks (paragraph-level) from assets + submissions + feedback
  models/
    search.py             # SearchScope model
    enums.py              # QueryIntent, RetrievalStrategy, etc.
  prompts/
    classifier.txt        # LLM classification prompt
    grounded_answer.txt   # LLM grounded answer prompt
  repositories/
    scope_repo.py         # Scope resolution SQL queries
    chunk_repo.py         # Hybrid retrieval: pgvector + ts_rank + pg_trgm
    search_repo.py        # Structured lookups (plays, submissions, feedback)
  tests/                  # 140 tests (7 files)

frontend/src/
  api.js                  # API client + SSE stream handler
  App.jsx                 # Main app component
  components/
    CompanySelect.jsx     # Company dropdown
    UserSelect.jsx        # User dropdown (filtered by company)
    SearchBar.jsx         # Search input
    AnswerStream.jsx      # Streaming answer display
    ThoughtTrace.jsx      # Collapsible classification trace
    Citations.jsx         # Color-coded citation chips

scripts/
  init_db.sh              # One-command setup (Postgres + tables + seed + chunks + embeddings)
```

---

## Bonus: Discussion Topics for Live Review

### Recommendation Engine

After each answer, recommend 2-3 follow-up Reps/Plays by:
1. Extracting the topic from the current query
2. Finding other reps in the user's assigned plays that share keywords
3. Prioritizing incomplete assignments (status != "completed")

### User Feedback & Self-Correction

- Add thumbs up/down to each answer, stored in a `feedback_signals` table
- Downvoted answers get the query + correct answer stored in a "Verified Truth" store
- On subsequent queries, check Verified Truth first before RAG retrieval
- Conflicting feedback from two experts: use recency + role-based priority (manager > rep)

### Prompt Refinement Pipeline

- Collect (query, retrieved_chunks, answer, user_feedback) tuples
- Identify patterns in downvoted answers (e.g., "always misclassifies submission queries")
- Generate improved few-shot examples from high-rated answers
- A/B test prompt variants using shadow scoring

### Scaling Considerations

- **Vector search at scale**: Current pgvector HNSW handles 187 chunks easily; for 100K+ chunks, consider Qdrant for dedicated ANN with filtering
- **Caching**: Cache ScopeResolver results per (company_id, user_id) — scope changes rarely
- **Async ingestion**: Background job for chunk building when new assets are uploaded
- **Multi-region**: Scope resolver naturally partitions by company_id — shard Postgres by company

---

## AI Usage

This project was built with **Claude Code** (Claude Opus). Key areas where AI accelerated development:

1. **Scope resolution logic**: Prompted Claude to trace the FK chain from the CSV data and generate the SQL queries + tests. The orphan FK detection and skip logic was identified by running the seed script and having Claude diagnose the integrity errors.

2. **Guardrail prompt tuning**: Iteratively refined the LLM classifier prompt by testing edge cases ("9 planets", "hello", "Streptococcus eradication rate") and adjusting the prompt until the classification matched the spec's three-tier guardrail requirements. The key insight — passing play titles to the classifier so it can determine domain relevance — came from debugging a misclassification.

---

## Tech Stack

| Component | Technology |
|---|---|
| Backend | Python 3.11+, FastAPI, SQLAlchemy |
| Database | PostgreSQL 16 (pgvector/pgvector:pg16) with pgvector + pg_trgm |
| Embeddings | sentence-transformers all-MiniLM-L6-v2 (384d) |
| LLM | Anthropic Claude (Sonnet 4) |
| Frontend | React, Vite |
| Infrastructure | Docker Compose |
| Testing | pytest (140 tests) |
