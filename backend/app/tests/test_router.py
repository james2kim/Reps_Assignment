"""
Tests for the retrieval router — verifies correct dispatch
to structured, document, or hybrid backends.

Runs against the real seeded database.
"""

import pytest

from backend.app.core.retrieval_router import route_query
from backend.app.core.scope_resolver import resolve_scope
from backend.app.db.session import SessionLocal
from backend.app.models.enums import RetrievalStrategy


@pytest.fixture()
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def frank_scope(db):
    return resolve_scope(db, "comp-hexaloom-005", "2c7i-106")


@pytest.fixture()
def empty_scope(db):
    return resolve_scope(db, "comp-hexaloom-005", "h0s4-544")


# -----------------------------------------------------------------------
# Structured dispatch
# -----------------------------------------------------------------------


class TestStructuredRoute:
    def test_score_query_returns_structured(self, db, frank_scope):
        result = route_query(db, "What was my score?", frank_scope)
        assert result.classification.strategy == RetrievalStrategy.STRUCTURED
        assert result.structured is not None
        assert len(result.structured.feedback) > 0
        assert result.chunks == []

    def test_plays_query_returns_plays(self, db, frank_scope):
        result = route_query(db, "What plays am I assigned to?", frank_scope)
        assert result.structured is not None
        assert len(result.structured.plays) == 3
        titles = {p.title for p in result.structured.plays}
        assert "The DNA of Materials" in titles

    def test_submissions_query(self, db, frank_scope):
        result = route_query(db, "What did I submit?", frank_scope)
        assert result.structured is not None
        assert len(result.structured.submissions) == 2

    def test_feedback_has_scores(self, db, frank_scope):
        result = route_query(db, "Show me my feedback", frank_scope)
        for fb in result.structured.feedback:
            assert fb.score > 0
            assert fb.text != ""


# -----------------------------------------------------------------------
# Document dispatch
# -----------------------------------------------------------------------


class TestDocumentRoute:
    def test_product_query_returns_chunks(self, db, frank_scope):
        result = route_query(db, "What is Hexenon?", frank_scope)
        assert result.classification.strategy == RetrievalStrategy.DOCUMENT
        assert result.structured is None
        assert len(result.chunks) > 0

    def test_chunks_are_scoped(self, db, frank_scope):
        result = route_query(db, "Hexenon molecular structure", frank_scope)
        for chunk in result.chunks:
            assert chunk.company_id == "comp-hexaloom-005"


# -----------------------------------------------------------------------
# Hybrid dispatch
# -----------------------------------------------------------------------


class TestHybridRoute:
    def test_improvement_query_returns_both(self, db, frank_scope):
        result = route_query(db, "How can I improve my pitch?", frank_scope)
        assert result.classification.strategy == RetrievalStrategy.HYBRID
        assert result.structured is not None
        assert not result.structured.is_empty
        # Chunks may or may not match — but structured should have feedback
        assert len(result.structured.feedback) > 0


# -----------------------------------------------------------------------
# None dispatch
# -----------------------------------------------------------------------


class TestNoneRoute:
    def test_out_of_scope_returns_empty(self, db, frank_scope):
        result = route_query(db, "What's the weather?", frank_scope)
        assert result.structured is None
        assert result.chunks == []
        assert not result.has_results

    def test_empty_scope_returns_empty(self, db, empty_scope):
        result = route_query(db, "What is Hexenon?", empty_scope)
        assert not result.has_results
