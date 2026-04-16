"""
Retrieval router: dispatches to structured lookup, document RAG, or both.

Document RAG pipeline:
  1. Scope filter (in SQL WHERE clause — already enforced)
  2. TopK candidates (retrieve more than we need)
  3. Relevance threshold (drop low-scoring chunks)
  4. Token budget (trim to fit LLM context window)
  5. Return filtered chunks for LLM context

Routes based on RetrievalStrategy from the classifier:
  - structured → SQL against relational tables
  - document   → chunk retrieval with pipeline above
  - hybrid     → both
  - none       → no retrieval
"""

from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.app.core.query_classifier import QueryClassification, classify_query
from backend.app.models.enums import RetrievalStrategy
from backend.app.models.search import SearchScope
from backend.app.repositories.chunk_repo import ChunkResult, retrieve_chunks
from backend.app.repositories.search_repo import StructuredResult, structured_lookup

# Pipeline config
TOP_K_CANDIDATES = 15  # fetch more candidates than we need
MIN_RELEVANCE_SCORE = 0.05  # drop chunks below this combined score
MAX_CONTEXT_TOKENS = 3000  # approximate token budget (chars / 4)
MAX_CHUNKS = 5  # hard cap on chunks sent to LLM


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token for English."""
    return len(text) // 4


def _apply_relevance_filter(chunks: list[ChunkResult]) -> list[ChunkResult]:
    """Drop chunks below the relevance threshold."""
    if not chunks:
        return []

    filtered = [c for c in chunks if c.rank_score >= MIN_RELEVANCE_SCORE]

    # Also drop chunks that score less than 20% of the top chunk
    # (relative threshold catches cases where top scores are high
    #  but there's a long tail of marginally relevant results)
    if filtered:
        top_score = filtered[0].rank_score
        cutoff = top_score * 0.2
        filtered = [c for c in filtered if c.rank_score >= cutoff]

    return filtered


def _apply_token_budget(chunks: list[ChunkResult]) -> list[ChunkResult]:
    """Trim chunks to fit within the token budget."""
    result = []
    total_tokens = 0

    for chunk in chunks:
        chunk_tokens = _estimate_tokens(chunk.content)
        if total_tokens + chunk_tokens > MAX_CONTEXT_TOKENS and result:
            # Already have some chunks and this one would exceed budget
            break
        result.append(chunk)
        total_tokens += chunk_tokens

        if len(result) >= MAX_CHUNKS:
            break

    return result


def _pipeline(chunks: list[ChunkResult]) -> list[ChunkResult]:
    """Apply the full retrieval pipeline: relevance filter → token budget."""
    chunks = _apply_relevance_filter(chunks)
    chunks = _apply_token_budget(chunks)
    return chunks


class RetrievalResult(BaseModel):
    classification: QueryClassification
    structured: StructuredResult | None = None
    chunks: list[ChunkResult] = []

    @property
    def has_results(self) -> bool:
        has_structured = self.structured is not None and not self.structured.is_empty
        has_chunks = len(self.chunks) > 0
        return has_structured or has_chunks


def route_query(
    db: Session,
    query: str,
    scope: SearchScope,
) -> RetrievalResult:
    """Classify, then dispatch to the appropriate retrieval backend(s)."""
    classification = classify_query(query, scope)
    strategy = classification.strategy

    structured = None
    chunks = []

    if strategy == RetrievalStrategy.STRUCTURED:
        structured = structured_lookup(db, scope)

    elif strategy == RetrievalStrategy.DOCUMENT:
        raw_chunks = retrieve_chunks(db, query, scope, limit=TOP_K_CANDIDATES)
        chunks = _pipeline(raw_chunks)

    elif strategy == RetrievalStrategy.HYBRID:
        structured = structured_lookup(db, scope)
        raw_chunks = retrieve_chunks(db, query, scope, limit=TOP_K_CANDIDATES)
        chunks = _pipeline(raw_chunks)

    # strategy == NONE → return empty

    return RetrievalResult(
        classification=classification,
        structured=structured,
        chunks=chunks,
    )
