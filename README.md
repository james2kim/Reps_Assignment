# BigSpring Enterprise Search Engine

Secure multi-tenant search engine with strict authorization scoping. Users can only search content from their assigned plays, their own submissions, and their own feedback.

## Prerequisites

- Python 3.11+
- Docker Desktop

## Setup

```bash
# 1. Start Postgres
docker compose up -d

# 2. Install dependencies
pip install -e ".[dev]"

# 3. Create tables
docker compose exec -T postgres psql -U postgres -d bigspring < backend/app/db/schema.sql

# 4. Seed relational data
python -m backend.app.ingestion.seed_relational_data
```

## Database

Postgres 16 running via Docker on `localhost:5432`. Connection: `postgresql://postgres:postgres@localhost:5432/bigspring`.

### Schema

9 tables with TEXT primary keys matching source CSV IDs:

| Table | Rows | Source | Dependencies |
|---|---|---|---|
| companies | 5 | JSON | none |
| users | 224 | CSV | companies |
| plays | 15 | CSV | companies |
| assets | 63 | CSV | companies |
| play_assignments | 82 | CSV | users, plays |
| reps | 37 | CSV | plays, companies, assets |
| submissions | 38 | CSV | users, reps, assets, companies |
| feedback | 38 | CSV | submissions, companies |
| search_chunks | - | ingestion | companies, assets |

### Authorization chain

```
user -> play_assignments -> plays -> reps (watch) -> assets -> search_chunks
user -> submissions -> feedback
```

### Data notes

Source CSVs contain orphan FK references (user `j0i9-305`, plays `hex-006..010`, rep `hex-024`). The seed script skips these rows and logs warnings. 20 total rows skipped across 4 tables.

## Project Structure

```
backend/app/
  db/           # schema.sql, session.py, SQLAlchemy models
  ingestion/    # seed_relational_data.py, asset parsing, chunking
  core/         # scope_resolver, query_classifier, retrieval, guardrails
  api/          # FastAPI routes and Pydantic schemas
  models/       # domain models and enums
  repositories/ # data access layer
  prompts/      # LLM prompt templates
  tests/        # unit and integration tests
```
