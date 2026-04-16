"""
Chunk retrieval from search_chunks with scope-based filtering.

Filtering happens FIRST (via WHERE clause), then ranking is applied
to the filtered set. This guarantees no cross-company or cross-user leakage.

Hybrid ranking combines three signals:
  1. Vector cosine similarity (semantic matching via pgvector)
  2. ts_rank full-text search (word matching with stemming)
  3. word_similarity from pg_trgm (fuzzy/typo matching)

Falls back to text-only ranking if embeddings are not yet generated.
"""

import json

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.app.models.search import SearchScope

# Lazy-loaded embedding model (loaded once on first use)
_model = None


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        from backend.app.config import settings

        _model = SentenceTransformer(settings.embedding_model)
    return _model


def _embed_query(query: str) -> list[float]:
    model = _get_model()
    return model.encode(query).tolist()


class ChunkResult(BaseModel):
    """A single retrieved chunk with citation metadata."""

    chunk_id: str
    content: str
    source_type: str  # "asset" or "history"
    source_id: str
    asset_id: str | None
    company_id: str
    metadata: dict
    rank_score: float


def _has_embeddings(db: Session) -> bool:
    """Check if any chunks have embeddings."""
    row = db.execute(
        text("SELECT EXISTS(SELECT 1 FROM search_chunks WHERE embedding IS NOT NULL)")
    ).scalar()
    return bool(row)


def retrieve_chunks(
    db: Session,
    query: str,
    scope: SearchScope,
    limit: int = 10,
) -> list[ChunkResult]:
    """
    Retrieve chunks filtered by scope, ranked by relevance.

    Uses vector similarity if embeddings exist, otherwise falls back
    to text-only ranking.
    """
    allowed_asset_ids = list(scope.allowed_asset_ids) or ["__none__"]
    allowed_history_ids = list(scope.allowed_submission_ids | scope.allowed_feedback_ids) or [
        "__none__"
    ]

    use_vectors = _has_embeddings(db)

    if use_vectors:
        query_embedding = _embed_query(query)
        return _retrieve_hybrid(
            db,
            query,
            query_embedding,
            allowed_asset_ids,
            allowed_history_ids,
            scope.company_id,
            limit,
        )
    else:
        return _retrieve_text_only(
            db,
            query,
            allowed_asset_ids,
            allowed_history_ids,
            scope.company_id,
            limit,
        )


def _retrieve_hybrid(
    db: Session,
    query: str,
    query_embedding: list[float],
    allowed_asset_ids: list[str],
    allowed_history_ids: list[str],
    company_id: str,
    limit: int,
) -> list[ChunkResult]:
    """Hybrid retrieval: vector similarity + text search + trigram."""
    stmt = text("""
        WITH scoped AS (
            SELECT
                id, content, source_type, source_id,
                asset_id, company_id, metadata, embedding
            FROM search_chunks
            WHERE company_id = :company_id
              AND (
                  (source_type = 'asset'   AND asset_id  = ANY(:asset_ids))
               OR (source_type = 'history' AND source_id = ANY(:history_ids))
              )
        ),
        ranked AS (
            SELECT
                id, content, source_type, source_id,
                asset_id, company_id, metadata,
                -- vector cosine similarity (0 to 1, higher is better)
                CASE WHEN embedding IS NOT NULL
                    THEN 1 - (embedding <=> CAST(:query_emb AS vector))
                    ELSE 0
                END AS vec_score,
                -- full-text rank
                ts_rank_cd(
                    to_tsvector('english', content),
                    plainto_tsquery('english', :query)
                ) AS ts_score,
                -- trigram similarity
                word_similarity(:query, content) AS trgm_score
            FROM scoped
        )
        SELECT
            id, content, source_type, source_id, asset_id,
            company_id, metadata,
            (COALESCE(vec_score, 0) * 3
             + COALESCE(ts_score, 0) * 2
             + COALESCE(trgm_score, 0)) AS rank_score
        FROM ranked
        WHERE vec_score > 0.2 OR ts_score > 0 OR trgm_score > 0.1
        ORDER BY rank_score DESC
        LIMIT :lim
    """)

    rows = db.execute(
        stmt,
        {
            "company_id": company_id,
            "asset_ids": allowed_asset_ids,
            "history_ids": allowed_history_ids,
            "query": query,
            "query_emb": str(query_embedding),
            "lim": limit,
        },
    ).all()

    return _parse_results(rows)


def _retrieve_text_only(
    db: Session,
    query: str,
    allowed_asset_ids: list[str],
    allowed_history_ids: list[str],
    company_id: str,
    limit: int,
) -> list[ChunkResult]:
    """Fallback: text-only retrieval when no embeddings exist."""
    stmt = text("""
        WITH scoped AS (
            SELECT
                id, content, source_type, source_id,
                asset_id, company_id, metadata
            FROM search_chunks
            WHERE company_id = :company_id
              AND (
                  (source_type = 'asset'   AND asset_id  = ANY(:asset_ids))
               OR (source_type = 'history' AND source_id = ANY(:history_ids))
              )
        ),
        ranked AS (
            SELECT
                *,
                ts_rank_cd(
                    to_tsvector('english', content),
                    plainto_tsquery('english', :query)
                ) AS ts_score,
                word_similarity(:query, content) AS trgm_score
            FROM scoped
        )
        SELECT
            id, content, source_type, source_id, asset_id,
            company_id, metadata,
            (COALESCE(ts_score, 0) * 2 + COALESCE(trgm_score, 0)) AS rank_score
        FROM ranked
        WHERE ts_score > 0 OR trgm_score > 0.1
        ORDER BY rank_score DESC
        LIMIT :lim
    """)

    rows = db.execute(
        stmt,
        {
            "company_id": company_id,
            "asset_ids": allowed_asset_ids,
            "history_ids": allowed_history_ids,
            "query": query,
            "lim": limit,
        },
    ).all()

    return _parse_results(rows)


def _parse_results(rows) -> list[ChunkResult]:
    results = []
    for row in rows:
        meta = row[6] if isinstance(row[6], dict) else json.loads(row[6])
        results.append(
            ChunkResult(
                chunk_id=row[0],
                content=row[1],
                source_type=row[2],
                source_id=row[3],
                asset_id=row[4],
                company_id=row[5],
                metadata=meta,
                rank_score=float(row[7]),
            )
        )
    return results
