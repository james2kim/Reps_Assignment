"""
Query classifier: determines intent AND retrieval strategy.

Two-layer approach:
  1. Rules handle HIGH-CONFIDENCE positive matches (product terms, structured lookups,
     history keywords). These are fast and bypass the LLM.
  2. Everything else goes to the LLM for classification. This catches out-of-scope,
     general professional, greetings, and ambiguous queries.

The key insight: rules should only ACCEPT queries into assigned_search.
The LLM should be the gatekeeper that REJECTS everything else.
Never default to assigned_search for unrecognized queries.
"""

import re
from pathlib import Path

import anthropic
from pydantic import BaseModel

from backend.app.config import settings
from backend.app.models.enums import QueryIntent, RetrievalStrategy
from backend.app.models.search import SearchScope


class QueryClassification(BaseModel):
    intent: QueryIntent
    strategy: RetrievalStrategy
    confidence: float  # 0.0 - 1.0
    reason: str


# ---------------------------------------------------------------------------
# Keyword sets — only used for high-confidence positive matches
# ---------------------------------------------------------------------------

_STRUCTURED_KEYWORDS = {
    "my score",
    "my scores",
    "my feedback",
    "my grade",
    "what plays",
    "assigned plays",
    "my plays",
    "my assignments",
    "what reps",
    "my reps",
    "pending reps",
    "incomplete",
    "how many submissions",
    "my submissions",
    "submission status",
    "assignment status",
    "what did i submit",
    "which plays",
}

_HISTORY_DOC_KEYWORDS = {
    "my submission",
    "my pitch",
    "my recording",
    "my response",
    "my practice",
    "my attempt",
    "what i said",
    "what did i say",
    "review my",
    "listen to my",
    "watch my",
}

_HYBRID_KEYWORDS = {
    "improve my",
    "how can i do better",
    "what went wrong",
    "based on my feedback",
    "compared to my score",
    "why did i get",
    "areas to improve",
}

_PRODUCT_KEYWORDS = {
    "hexenon",
    "hexenon-s",
    "hexenon-m",
    "hexenon-x",
    "hexenon-lite",
    "synthetic sinew",
    "neuro-linker",
    "lattice-stack",
    "indestru-poly",
    "hexaloom",
    "nanoworks",
    "nanotube",
    "carbon nanotube",
    "amproxin",
    "zaloric",
    "lydrenex",
    "veldra",
    "somnirel",
    "nuvia",
    "aetheris",
    "aether-blend",
    "gridmaster",
    "k-stream",
    "vorex",
    "kyberon",
    "lumina",
    "sentilink",
    "sentivue",
}


def _normalize(query: str) -> str:
    return query.lower().strip()


def _has_match(query: str, keywords: set[str]) -> bool:
    return any(kw in query for kw in keywords)


# ---------------------------------------------------------------------------
# LLM classifier
# ---------------------------------------------------------------------------

_PROMPT = Path("backend/app/prompts/classifier.txt").read_text()


def _build_scope_context(scope: SearchScope) -> str:
    """Build a scope summary with play titles so the LLM knows what materials the user has."""
    parts = []
    if scope.play_titles:
        titles = ", ".join(scope.play_titles)
        parts.append(f"User has {len(scope.play_titles)} assigned training plays: {titles}.")
    else:
        parts.append("User has NO assigned plays or materials.")
    if scope.allowed_submission_ids:
        parts.append(f"User has {len(scope.allowed_submission_ids)} practice submissions.")
    if scope.allowed_feedback_ids:
        parts.append(f"User has {len(scope.allowed_feedback_ids)} feedback entries.")
    if scope.is_empty:
        parts.append("User has no materials at all.")
    return " ".join(parts)


def _classify_with_llm(query: str, scope: SearchScope) -> QueryClassification:
    """Call the LLM to classify the query."""
    api_key = settings.anthropic_api_key
    if not api_key:
        # No API key — conservative fallback: treat as out_of_scope
        return QueryClassification(
            intent=QueryIntent.OUT_OF_SCOPE,
            strategy=RetrievalStrategy.NONE,
            confidence=0.5,
            reason="No LLM available — defaulting to out_of_scope for safety",
        )

    scope_ctx = _build_scope_context(scope)
    user_msg = f"User context: {scope_ctx}\n\nQuery: {query}"

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=50,
        system=_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
    )

    label = response.content[0].text.strip().lower().replace(" ", "_")

    try:
        intent = QueryIntent(label)
    except ValueError:
        # LLM returned unexpected label — safe fallback
        return QueryClassification(
            intent=QueryIntent.OUT_OF_SCOPE,
            strategy=RetrievalStrategy.NONE,
            confidence=0.5,
            reason=f"LLM returned unrecognized label: {label}",
        )

    # Map intent to strategy
    strategy = _intent_to_strategy(intent, scope)

    return QueryClassification(
        intent=intent,
        strategy=strategy,
        confidence=0.85,
        reason=f"Classified by LLM as {intent}",
    )


def _intent_to_strategy(intent: QueryIntent, scope: SearchScope) -> RetrievalStrategy:
    """Map an intent to the appropriate retrieval strategy."""
    if intent in (
        QueryIntent.OUT_OF_SCOPE,
        QueryIntent.GENERAL_PROFESSIONAL,
        QueryIntent.PROPRIETARY_UNGROUNDED,
    ):
        return RetrievalStrategy.NONE
    # assigned_search — default to document
    return RetrievalStrategy.DOCUMENT


# ---------------------------------------------------------------------------
# Main classifier — rules first, then LLM
# ---------------------------------------------------------------------------


def classify_query(query: str, scope: SearchScope) -> QueryClassification:
    """
    Classify a query. Rules handle high-confidence positive matches.
    Everything else goes to the LLM.
    """
    q = _normalize(query)

    # --- Rule layer: only ACCEPT into assigned_search for clear matches ---

    # 1. Hybrid — needs structured facts + document grounding
    if _has_match(q, _HYBRID_KEYWORDS):
        if scope.allowed_submission_ids:
            return QueryClassification(
                intent=QueryIntent.ASSIGNED_SEARCH,
                strategy=RetrievalStrategy.HYBRID,
                confidence=0.85,
                reason="Query needs both structured data and document content",
            )
        # Has hybrid keywords but no submissions — let LLM decide
        return _classify_with_llm(query, scope)

    # 2. Structured lookup — facts in relational tables
    if _has_match(q, _STRUCTURED_KEYWORDS):
        if not scope.is_empty or scope.allowed_submission_ids or scope.allowed_feedback_ids:
            return QueryClassification(
                intent=QueryIntent.ASSIGNED_SEARCH,
                strategy=RetrievalStrategy.STRUCTURED,
                confidence=0.9,
                reason="Query asks for structured data (scores, assignments, statuses)",
            )
        return _classify_with_llm(query, scope)

    # 3. History document — submission/feedback transcript content
    if _has_match(q, _HISTORY_DOC_KEYWORDS):
        if scope.allowed_submission_ids:
            return QueryClassification(
                intent=QueryIntent.ASSIGNED_SEARCH,
                strategy=RetrievalStrategy.DOCUMENT,
                confidence=0.85,
                reason="Query references submission content for document retrieval",
            )
        return _classify_with_llm(query, scope)

    # 4. Product/material keywords — high confidence assigned_search
    if _has_match(q, _PRODUCT_KEYWORDS):
        if scope.is_empty:
            return QueryClassification(
                intent=QueryIntent.PROPRIETARY_UNGROUNDED,
                strategy=RetrievalStrategy.NONE,
                confidence=0.8,
                reason="Query mentions proprietary terms but user has no assigned materials",
            )
        return QueryClassification(
            intent=QueryIntent.ASSIGNED_SEARCH,
            strategy=RetrievalStrategy.DOCUMENT,
            confidence=0.9,
            reason="Query matches product terms — retrieving from training documents",
        )

    # --- No positive match — LLM decides ---
    return _classify_with_llm(query, scope)
