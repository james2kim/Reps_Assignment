"""
Tests for answer generation and citation formatting.

Tests the full pipeline: scope → classify → retrieve → generate answer.
LLM calls are tested without a client (fallback mode).
"""

import pytest

from backend.app.core.answer_generator import generate_answer
from backend.app.core.citations import build_citations
from backend.app.core.guardrails import (
    GENERAL_PROFESSIONAL_DISCLAIMER,
    NO_RESULTS_RESPONSE,
    OUT_OF_SCOPE_RESPONSE,
    PROPRIETARY_UNGROUNDED_RESPONSE,
)
from backend.app.core.retrieval_router import route_query
from backend.app.core.scope_resolver import resolve_scope
from backend.app.db.session import SessionLocal
from backend.app.models.enums import QueryIntent, RetrievalStrategy
from backend.app.repositories.chunk_repo import retrieve_chunks


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
# Guardrail responses
# -----------------------------------------------------------------------


class TestGuardrails:
    def test_out_of_scope_exact_text(self, db, frank_scope):
        retrieval = route_query(db, "Tell me a joke", frank_scope)
        resp = generate_answer(db, "Tell me a joke", retrieval)
        assert resp.answer == OUT_OF_SCOPE_RESPONSE
        assert resp.citations == []
        assert resp.disclaimer is None

    def test_proprietary_ungrounded_exact_text(self, db, empty_scope):
        retrieval = route_query(db, "What is Hexenon?", empty_scope)
        resp = generate_answer(db, "What is Hexenon?", retrieval)
        assert resp.answer == PROPRIETARY_UNGROUNDED_RESPONSE
        assert resp.citations == []

    def test_general_professional_has_disclaimer(self, db, frank_scope):
        retrieval = route_query(db, "What is SPIN selling?", frank_scope)
        resp = generate_answer(db, "What is SPIN selling?", retrieval)
        assert resp.disclaimer == GENERAL_PROFESSIONAL_DISCLAIMER
        assert resp.citations == []

    def test_no_results_fallback(self, db, frank_scope):
        """If classified as assigned_search but retrieval returns nothing."""
        # Craft a retrieval result with no chunks and no structured data
        from backend.app.core.query_classifier import QueryClassification
        from backend.app.core.retrieval_router import RetrievalResult

        retrieval = RetrievalResult(
            classification=QueryClassification(
                intent=QueryIntent.ASSIGNED_SEARCH,
                strategy=RetrievalStrategy.DOCUMENT,
                confidence=0.5,
                reason="test",
            ),
            chunks=[],
            structured=None,
        )
        resp = generate_answer(db, "xyzzy nonexistent topic", retrieval)
        assert resp.answer == NO_RESULTS_RESPONSE


# -----------------------------------------------------------------------
# Grounded answer (no LLM — fallback mode)
# -----------------------------------------------------------------------


class TestGroundedAnswer:
    def test_product_query_returns_content(self, db, frank_scope):
        retrieval = route_query(db, "What is Hexenon?", frank_scope)
        resp = generate_answer(db, "What is Hexenon?", retrieval)
        # Without LLM, fallback includes raw context
        assert "assigned materials" in resp.answer.lower()
        assert len(resp.citations) > 0

    def test_structured_query_returns_data(self, db, frank_scope):
        retrieval = route_query(db, "What was my score?", frank_scope)
        resp = generate_answer(db, "What was my score?", retrieval)
        assert "assigned materials" in resp.answer.lower() or "FEEDBACK" in resp.answer


# -----------------------------------------------------------------------
# Thought trace
# -----------------------------------------------------------------------


class TestThoughtTrace:
    def test_trace_fields_present(self, db, frank_scope):
        retrieval = route_query(db, "What is Hexenon?", frank_scope)
        resp = generate_answer(db, "What is Hexenon?", retrieval)
        trace = resp.thought_trace
        assert trace.intent == QueryIntent.ASSIGNED_SEARCH
        assert trace.strategy == RetrievalStrategy.DOCUMENT
        assert 0.0 <= trace.confidence <= 1.0
        assert trace.chunks_retrieved > 0

    def test_trace_for_guardrail(self, db, frank_scope):
        retrieval = route_query(db, "Give me a recipe", frank_scope)
        resp = generate_answer(db, "Give me a recipe", retrieval)
        assert resp.thought_trace.intent == QueryIntent.OUT_OF_SCOPE
        assert resp.thought_trace.strategy == RetrievalStrategy.NONE
        assert resp.thought_trace.chunks_retrieved == 0


# -----------------------------------------------------------------------
# Citation formatting
# -----------------------------------------------------------------------


class TestCitations:
    def test_pdf_citation_format(self, db, frank_scope):
        chunks = retrieve_chunks(db, "Hexenon molecular structure", frank_scope)
        citations = build_citations(db, chunks)
        pdf_citations = [c for c in citations if c.source_type == "pdf"]
        assert len(pdf_citations) > 0
        for c in pdf_citations:
            assert c.label.startswith("[PDF:")
            assert c.source_file.endswith(".pdf")

    def test_pdf_citation_has_page(self, db, frank_scope):
        chunks = retrieve_chunks(db, "Hexenon molecular structure", frank_scope)
        citations = build_citations(db, chunks)
        pdf_with_page = [c for c in citations if c.source_type == "pdf" and c.page]
        assert len(pdf_with_page) > 0
        for c in pdf_with_page:
            assert "Page" in c.label

    def test_video_citation_format(self, db, frank_scope):
        chunks = retrieve_chunks(db, "Synthetic Sinew robotics", frank_scope)
        citations = build_citations(db, chunks)
        video_citations = [c for c in citations if c.source_type == "video"]
        if video_citations:
            for c in video_citations:
                assert c.label.startswith("[Video:")
                assert c.source_file.endswith(".mp4")

    def test_feedback_citation_format(self, db, frank_scope):
        chunks = retrieve_chunks(db, "Feedback score conductivity", frank_scope)
        citations = build_citations(db, chunks)
        fb_citations = [c for c in citations if c.source_type == "feedback"]
        if fb_citations:
            for c in fb_citations:
                assert "score" in c.label.lower()
                assert "/10" in c.label

    def test_citations_are_deduplicated(self, db, frank_scope):
        chunks = retrieve_chunks(db, "Hexenon", frank_scope, limit=20)
        citations = build_citations(db, chunks)
        labels = [c.label for c in citations]
        assert len(labels) == len(set(labels))
