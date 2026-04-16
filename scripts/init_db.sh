#!/usr/bin/env bash
set -e

echo "=== BigSpring Search Engine — Database Setup ==="
echo ""

# 1. Start Postgres
echo "[1/5] Starting Postgres..."
docker compose up -d
sleep 3

# 2. Enable extensions
echo "[2/5] Enabling extensions..."
docker compose exec -T postgres psql -U postgres -d bigspring -c "CREATE EXTENSION IF NOT EXISTS vector;"
docker compose exec -T postgres psql -U postgres -d bigspring -c "CREATE EXTENSION IF NOT EXISTS pg_trgm;"

# 3. Create tables
echo "[3/5] Creating tables..."
docker compose exec -T postgres psql -U postgres -d bigspring < backend/app/db/schema.sql

# 4. Create indexes for search
echo "[4/5] Creating search indexes..."
docker compose exec -T postgres psql -U postgres -d bigspring -c "CREATE INDEX IF NOT EXISTS idx_chunks_content_trgm ON search_chunks USING gin (content gin_trgm_ops);"
docker compose exec -T postgres psql -U postgres -d bigspring -c "CREATE INDEX IF NOT EXISTS idx_chunks_embedding ON search_chunks USING hnsw (embedding vector_cosine_ops);"

# 5. Seed data + build chunks + embed
echo "[5/5] Seeding data and building search chunks..."
python3 -m backend.app.ingestion.seed_relational_data
python3 -m backend.app.ingestion.build_chunks
python3 -m backend.app.ingestion.embed_chunks

echo ""
echo "=== Setup complete ==="
docker compose exec -T postgres psql -U postgres -d bigspring -c "
SELECT 'companies' as t, count(*) FROM companies
UNION ALL SELECT 'users', count(*) FROM users
UNION ALL SELECT 'plays', count(*) FROM plays
UNION ALL SELECT 'assets', count(*) FROM assets
UNION ALL SELECT 'play_assignments', count(*) FROM play_assignments
UNION ALL SELECT 'reps', count(*) FROM reps
UNION ALL SELECT 'submissions', count(*) FROM submissions
UNION ALL SELECT 'feedback', count(*) FROM feedback
UNION ALL SELECT 'search_chunks', count(*) FROM search_chunks
ORDER BY t;
"
