"""
Tests for query classifier.

Rule-based fast paths (no LLM needed):
  - Product keywords → assigned_search/document
  - Structured keywords → assigned_search/structured
  - History keywords → assigned_search/document
  - Hybrid keywords → assigned_search/hybrid
  - Proprietary ungrounded → product keywords + empty scope

LLM-dependent paths (require ANTHROPIC_API_KEY):
  - Out of scope detection
  - General professional detection
  - Ambiguous query handling
"""

import pytest

from backend.app.config import settings
from backend.app.core.query_classifier import classify_query
from backend.app.models.enums import QueryIntent, RetrievalStrategy
from backend.app.models.search import SearchScope

requires_llm = pytest.mark.skipif(
    not settings.anthropic_api_key,
    reason="ANTHROPIC_API_KEY not set",
)


@pytest.fixture()
def frank_scope() -> SearchScope:
    return SearchScope(
        company_id="comp-hexaloom-005",
        user_id="2c7i-106",
        allowed_play_ids={"play-hex-001", "play-hex-002", "play-hex-005"},
        allowed_rep_ids={"rep-hex-001", "rep-hex-003", "rep-hex-014"},
        allowed_asset_ids={
            "ast-hex-001",
            "ast-hex-002",
            "ast-hex-009",
            "ast-hex-sub-001",
            "ast-hex-sub-007",
        },
        allowed_submission_ids={"sub-hex-001", "sub-hex-007"},
        allowed_feedback_ids={"fb-hex-001", "fb-hex-007"},
    )


@pytest.fixture()
def empty_scope() -> SearchScope:
    return SearchScope(
        company_id="comp-hexaloom-005",
        user_id="h0s4-544",
        allowed_play_ids=set(),
        allowed_rep_ids=set(),
        allowed_asset_ids=set(),
        allowed_submission_ids=set(),
        allowed_feedback_ids=set(),
    )


# -----------------------------------------------------------------------
# Rule-based: product keywords (no LLM needed)
# -----------------------------------------------------------------------


class TestProductKeywords:
    def test_product_query(self, frank_scope):
        r = classify_query("What is Hexenon?", frank_scope)
        assert r.intent == QueryIntent.ASSIGNED_SEARCH
        assert r.strategy == RetrievalStrategy.DOCUMENT

    def test_product_variant(self, frank_scope):
        r = classify_query("How does Hexenon-S work in robotics?", frank_scope)
        assert r.intent == QueryIntent.ASSIGNED_SEARCH
        assert r.strategy == RetrievalStrategy.DOCUMENT

    def test_product_empty_scope(self, empty_scope):
        r = classify_query("What is Hexenon?", empty_scope)
        assert r.intent == QueryIntent.PROPRIETARY_UNGROUNDED
        assert r.strategy == RetrievalStrategy.NONE


# -----------------------------------------------------------------------
# Rule-based: structured keywords (no LLM needed)
# -----------------------------------------------------------------------


class TestStructuredKeywords:
    def test_score_query(self, frank_scope):
        r = classify_query("What was my score?", frank_scope)
        assert r.intent == QueryIntent.ASSIGNED_SEARCH
        assert r.strategy == RetrievalStrategy.STRUCTURED

    def test_assignments_query(self, frank_scope):
        r = classify_query("What plays am I assigned to?", frank_scope)
        assert r.strategy == RetrievalStrategy.STRUCTURED

    def test_submissions_query(self, frank_scope):
        r = classify_query("How many submissions have I done?", frank_scope)
        assert r.strategy == RetrievalStrategy.STRUCTURED


# -----------------------------------------------------------------------
# Rule-based: history keywords (no LLM needed)
# -----------------------------------------------------------------------


class TestHistoryKeywords:
    def test_submission_content(self, frank_scope):
        r = classify_query("Review my pitch recording", frank_scope)
        assert r.intent == QueryIntent.ASSIGNED_SEARCH
        assert r.strategy == RetrievalStrategy.DOCUMENT


# -----------------------------------------------------------------------
# Rule-based: hybrid keywords (no LLM needed)
# -----------------------------------------------------------------------


class TestHybridKeywords:
    def test_improve_query(self, frank_scope):
        r = classify_query("How can I improve my pitch?", frank_scope)
        assert r.strategy == RetrievalStrategy.HYBRID

    def test_feedback_based(self, frank_scope):
        r = classify_query("What went wrong based on my feedback?", frank_scope)
        assert r.strategy == RetrievalStrategy.HYBRID


# -----------------------------------------------------------------------
# LLM-dependent: out of scope, general professional, ambiguous
# -----------------------------------------------------------------------


@requires_llm
class TestLLMClassification:
    def test_out_of_scope_greeting(self, frank_scope):
        r = classify_query("Hello", frank_scope)
        assert r.intent == QueryIntent.OUT_OF_SCOPE

    def test_out_of_scope_joke(self, frank_scope):
        r = classify_query("Tell me a joke", frank_scope)
        assert r.intent == QueryIntent.OUT_OF_SCOPE

    def test_out_of_scope_cake(self, frank_scope):
        r = classify_query("How do I make a chocolate cake?", frank_scope)
        assert r.intent == QueryIntent.OUT_OF_SCOPE

    def test_general_professional_sales(self, frank_scope):
        r = classify_query("How do I handle price objections?", frank_scope)
        assert r.intent == QueryIntent.GENERAL_PROFESSIONAL

    def test_science_query_with_materials(self, frank_scope):
        """'What is a molecule?' — could relate to Hexaloom materials or be out_of_scope."""
        r = classify_query("What is a molecule?", frank_scope)
        assert r.intent in (QueryIntent.ASSIGNED_SEARCH, QueryIntent.OUT_OF_SCOPE)

    def test_general_knowledge_earth(self, frank_scope):
        r = classify_query("Why is the world round?", frank_scope)
        assert r.intent == QueryIntent.OUT_OF_SCOPE

    def test_ambiguous_no_materials(self, empty_scope):
        r = classify_query("tell me more", empty_scope)
        assert r.intent in (QueryIntent.OUT_OF_SCOPE, QueryIntent.GENERAL_PROFESSIONAL)
        assert r.strategy == RetrievalStrategy.NONE


# -----------------------------------------------------------------------
# Metadata
# -----------------------------------------------------------------------


class TestMetadata:
    def test_confidence_bounded(self, frank_scope):
        r = classify_query("What is Hexenon?", frank_scope)
        assert 0.0 <= r.confidence <= 1.0

    def test_reason_present(self, frank_scope):
        r = classify_query("What is Hexenon?", frank_scope)
        assert len(r.reason) > 0
