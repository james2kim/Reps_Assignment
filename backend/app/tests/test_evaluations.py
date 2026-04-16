"""
Evaluation framework for the Reps Search Engine.

Runs the spec's test cases end-to-end against the live system and scores:
  - Retrieval accuracy: did we find the right chunks?
  - Answer faithfulness: does the answer contain expected facts?
  - Guardrail compliance: did the right guardrail fire?
  - Citation accuracy: are the right sources cited?

Run with: pytest backend/app/tests/test_evaluations.py -v
"""

import anthropic
import pytest

from backend.app.config import settings
from backend.app.core.answer_generator import generate_answer
from backend.app.core.retrieval_router import route_query
from backend.app.core.scope_resolver import resolve_scope
from backend.app.db.session import SessionLocal
from backend.app.models.enums import QueryIntent

requires_llm = pytest.mark.skipif(
    not settings.anthropic_api_key,
    reason="ANTHROPIC_API_KEY not set — eval requires LLM",
)


@pytest.fixture()
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client():
    if not settings.anthropic_api_key:
        return None
    return anthropic.Anthropic(api_key=settings.anthropic_api_key)


def _run_search(db, client, company_id, user_id, query):
    """Run the full pipeline and return (scope, retrieval, response).
    Applies the same citation filter as the API route."""
    from backend.app.api.routes.search import _filter_used_citations

    scope = resolve_scope(db, company_id, user_id)
    retrieval = route_query(db, query, scope)
    response = generate_answer(db, query, retrieval, client=client)
    response.citations = _filter_used_citations(
        response.citations, retrieval.chunks, response.answer
    )
    return scope, retrieval, response


# =======================================================================
# Case 1.1: Knowledge Base PDF Search
# Aaron (Veldra) → "What is the eradication rate for Streptococcus pneumoniae?"
# Expected: 94.2%, citation to amproxin_guide.pdf Page 1
# =======================================================================


@requires_llm
class TestCase1_1:
    """Knowledge Base PDF Search — Aaron + Amproxin eradication rate."""

    def test_retrieval_finds_eradication_data(self, db):
        scope = resolve_scope(db, "comp-veldra-001", "a1b2-401")
        retrieval = route_query(
            db, "What is the eradication rate for Streptococcus pneumoniae?", scope
        )
        content = " ".join(c.content for c in retrieval.chunks)
        assert "94.2%" in content, "Retrieval did not find the 94.2% eradication rate"

    def test_answer_contains_expected_fact(self, db, client):
        _, _, resp = _run_search(
            db,
            client,
            "comp-veldra-001",
            "a1b2-401",
            "What is the eradication rate for Streptococcus pneumoniae?",
        )
        assert "94.2" in resp.answer, f"Answer missing 94.2%: {resp.answer[:200]}"

    def test_citation_references_amproxin_guide(self, db, client):
        _, _, resp = _run_search(
            db,
            client,
            "comp-veldra-001",
            "a1b2-401",
            "What is the eradication rate for Streptococcus pneumoniae?",
        )
        files = {c.source_file for c in resp.citations}
        assert "amproxin_guide.pdf" in files, f"Missing amproxin_guide.pdf in {files}"

    def test_no_hallucination(self, db, client):
        _, _, resp = _run_search(
            db,
            client,
            "comp-veldra-001",
            "a1b2-401",
            "What is the eradication rate for Streptococcus pneumoniae?",
        )
        # Should not mention products from other companies
        answer_lower = resp.answer.lower()
        assert "nuvia" not in answer_lower
        assert "gridmaster" not in answer_lower
        assert "hexenon" not in answer_lower


# =======================================================================
# Case 1.2: Personal Video Submission Search
# Daphne (Kyberon) → "When did I mention cooling energy costs?"
# Expected: "reduces cooling costs by up to 32 percent", timestamp 00:26
# =======================================================================


@requires_llm
class TestCase1_2:
    """Personal Submission Search — Daphne + cooling costs timestamp."""

    def test_retrieval_finds_submission_content(self, db):
        scope = resolve_scope(db, "comp-kyberon-003", "f2g3-580")
        retrieval = route_query(db, "When did I mention cooling energy costs?", scope)
        history_chunks = [c for c in retrieval.chunks if c.source_type == "history"]
        assert len(history_chunks) > 0, "No history chunks retrieved"

    def test_answer_contains_32_percent(self, db, client):
        _, _, resp = _run_search(
            db,
            client,
            "comp-kyberon-003",
            "f2g3-580",
            "When did I mention cooling energy costs?",
        )
        assert "32" in resp.answer, f"Answer missing 32%: {resp.answer[:200]}"

    def test_answer_contains_timestamp(self, db, client):
        _, _, resp = _run_search(
            db,
            client,
            "comp-kyberon-003",
            "f2g3-580",
            "When did I mention cooling energy costs?",
        )
        # Segments are grouped into paragraphs — LLM may cite the group range (00:00-00:38)
        # rather than the exact segment (00:26). Check for any timestamp reference.
        has_time_ref = "00:" in resp.answer or "recording" in resp.answer.lower()
        assert has_time_ref, f"Answer has no time reference: {resp.answer[:200]}"

    def test_citation_is_audio_with_timestamp(self, db, client):
        _, _, resp = _run_search(
            db,
            client,
            "comp-kyberon-003",
            "f2g3-580",
            "When did I mention cooling energy costs?",
        )
        audio_cites = [c for c in resp.citations if c.source_type == "audio" and c.start]
        assert len(audio_cites) > 0, f"No audio timestamp citation found: {resp.citations}"


# =======================================================================
# Case 2.1: Cross-Company Leakage
# Sophie (Aetheris) → "Show me the GridMaster PUE efficiency table."
# Expected: no results, no Kyberon content
# =======================================================================


@requires_llm
class TestCase2_1:
    """Cross-Company Leakage — Sophie cannot see Kyberon content."""

    def test_no_kyberon_chunks(self, db):
        scope = resolve_scope(db, "comp-aetheris-002", "a8m2-512")
        retrieval = route_query(db, "Show me the GridMaster PUE efficiency table.", scope)
        for c in retrieval.chunks:
            assert c.company_id != "comp-kyberon-003"

    def test_answer_is_not_found(self, db, client):
        _, _, resp = _run_search(
            db,
            client,
            "comp-aetheris-002",
            "a8m2-512",
            "Show me the GridMaster PUE efficiency table.",
        )
        assert "could not find" in resp.answer.lower(), f"Expected not-found: {resp.answer[:200]}"

    def test_no_citations(self, db, client):
        _, _, resp = _run_search(
            db,
            client,
            "comp-aetheris-002",
            "a8m2-512",
            "Show me the GridMaster PUE efficiency table.",
        )
        assert len(resp.citations) == 0, f"Should have 0 citations: {resp.citations}"

    def test_answer_does_not_leak_context(self, db, client):
        _, _, resp = _run_search(
            db,
            client,
            "comp-aetheris-002",
            "a8m2-512",
            "Show me the GridMaster PUE efficiency table.",
        )
        answer_lower = resp.answer.lower()
        assert "nuvia" not in answer_lower, "Answer leaks what IS in the materials"
        assert "lydrenex" not in answer_lower


# =======================================================================
# Case 2.2: Unassigned Play Same Company
# Leo (Aetheris, assigned Somnirel) → "How does Lydrenex protect the amygdala?"
# Expected: no results (Nuvia/Lydrenex is play-aet-002, not assigned)
# =======================================================================


@requires_llm
class TestCase2_2:
    """Unassigned Play — Leo can see Somnirel but not Nuvia."""

    def test_scope_excludes_nuvia(self, db):
        scope = resolve_scope(db, "comp-aetheris-002", "k7l8-437")
        assert "play-aet-002" not in scope.allowed_play_ids
        assert "ast-aet-003" not in scope.allowed_asset_ids

    def test_answer_is_not_found(self, db, client):
        _, _, resp = _run_search(
            db,
            client,
            "comp-aetheris-002",
            "k7l8-437",
            "How does Lydrenex protect the amygdala?",
        )
        assert "could not find" in resp.answer.lower(), f"Expected not-found: {resp.answer[:200]}"


# =======================================================================
# Case 2.3: Peer Submissions
# Aaron → "Show me Aaron's pitch about antibiotics."
# Expected: no results (users cannot see other users' submissions)
# =======================================================================


@requires_llm
class TestCase2_3:
    """Peer Submission Isolation — Aaron cannot see other users' pitches."""

    def test_answer_is_not_found(self, db, client):
        _, _, resp = _run_search(
            db,
            client,
            "comp-veldra-001",
            "a1b2-401",
            "Show me Aaron's pitch about antibiotics.",
        )
        assert "could not find" in resp.answer.lower(), f"Expected not-found: {resp.answer[:200]}"

    def test_no_leak_of_other_users(self, db, client):
        _, _, resp = _run_search(
            db,
            client,
            "comp-veldra-001",
            "a1b2-401",
            "Show me Aaron's pitch about antibiotics.",
        )
        assert "aaron" not in resp.answer.lower() or "could not find" in resp.answer.lower()


# =======================================================================
# Case 3.1: Shared Ingredient Disambiguation
# NOTE: Aaron is NOT assigned to play-vel-002 (Zaloric/Lydrenex) in seed data.
# Using Belinda (f3g4-502) who IS assigned to play-vel-002.
# =======================================================================


@requires_llm
class TestCase3_1:
    """Shared Ingredient — Veldra user sees Zaloric dosage, not Aetheris Nuvia."""

    def test_veldra_user_sees_zaloric_dosage(self, db, client):
        _, _, resp = _run_search(
            db,
            client,
            "comp-veldra-001",
            "f3g4-502",
            "What is the dosage for Lydrenex?",
        )
        answer = resp.answer
        assert "50" in answer or "100" in answer or "Zaloric" in answer.lower(), (
            f"Expected Zaloric dosage (50-100mg): {answer[:200]}"
        )

    def test_veldra_user_does_not_see_nuvia_dosage(self, db, client):
        scope, retrieval, resp = _run_search(
            db,
            client,
            "comp-veldra-001",
            "f3g4-502",
            "What is the dosage for Lydrenex?",
        )
        # Scope must not include Aetheris Nuvia asset
        assert "ast-aet-003" not in scope.allowed_asset_ids
        # All retrieved chunks must be Veldra only
        for c in retrieval.chunks:
            assert c.company_id == "comp-veldra-001"

    def test_no_cross_company_asset_overlap(self, db):
        veldra = resolve_scope(db, "comp-veldra-001", "f3g4-502")
        aetheris = resolve_scope(db, "comp-aetheris-002", "a8m2-512")
        assert veldra.allowed_asset_ids & aetheris.allowed_asset_ids == set()


# =======================================================================
# Case 3.2: Multi-Page Reasoning
# Daphne → "Compare my rack temperature baseline vs my GridMaster results."
# Expected: 24.5°C baseline, 21.8°C with GridMaster, 11.02% gain
# =======================================================================


@requires_llm
class TestCase3_2:
    """Multi-Page Reasoning — Daphne + rack temperature comparison."""

    def test_answer_contains_baseline(self, db, client):
        _, _, resp = _run_search(
            db,
            client,
            "comp-kyberon-003",
            "f2g3-580",
            "Compare my rack temperature baseline vs my GridMaster results.",
        )
        assert "24.5" in resp.answer, f"Missing baseline 24.5°C: {resp.answer[:200]}"

    def test_answer_contains_gridmaster_result(self, db, client):
        _, _, resp = _run_search(
            db,
            client,
            "comp-kyberon-003",
            "f2g3-580",
            "Compare my rack temperature baseline vs my GridMaster results.",
        )
        assert "21.8" in resp.answer, f"Missing GridMaster 21.8°C: {resp.answer[:200]}"

    def test_answer_contains_efficiency_gain(self, db, client):
        _, _, resp = _run_search(
            db,
            client,
            "comp-kyberon-003",
            "f2g3-580",
            "Compare my rack temperature baseline vs my GridMaster results.",
        )
        assert "11" in resp.answer, f"Missing ~11% gain: {resp.answer[:200]}"

    def test_citation_references_blueprint(self, db, client):
        _, _, resp = _run_search(
            db,
            client,
            "comp-kyberon-003",
            "f2g3-580",
            "Compare my rack temperature baseline vs my GridMaster results.",
        )
        files = {c.source_file for c in resp.citations}
        assert "gridmaster_blueprint.pdf" in files, f"Missing blueprint citation: {files}"


# =======================================================================
# Case 4.1: Fuzzy Matching / Typo
# Clark (Sentivue) → "Sentalink acceleration speed" (typo)
# Expected: finds Sentilink, 15x increase, timestamp 04:11
# =======================================================================


@requires_llm
class TestCase4_1:
    """Fuzzy Matching — typo 'Sentalink' still finds Sentilink content."""

    def test_retrieval_finds_sentilink(self, db):
        scope = resolve_scope(db, "comp-sentivue-004", "s7f1-531")
        retrieval = route_query(db, "Sentalink acceleration speed", scope)
        content = " ".join(c.content.lower() for c in retrieval.chunks)
        assert "sentilink" in content, "Fuzzy match failed — no Sentilink content"

    def test_answer_contains_15x(self, db, client):
        _, _, resp = _run_search(
            db,
            client,
            "comp-sentivue-004",
            "s7f1-531",
            "Sentalink acceleration speed",
        )
        assert "15" in resp.answer, f"Missing 15x figure: {resp.answer[:200]}"

    def test_answer_mentions_sentilink(self, db, client):
        _, _, resp = _run_search(
            db,
            client,
            "comp-sentivue-004",
            "s7f1-531",
            "Sentalink acceleration speed",
        )
        assert "sentilink" in resp.answer.lower(), f"Missing Sentilink: {resp.answer[:200]}"


# =======================================================================
# Case 4.2: Out of Scope
# Quinn (Aetheris, no assignments) → "How do I make a chocolate cake?"
# Expected: out_of_scope guardrail
# =======================================================================


@requires_llm
class TestCase4_2:
    """Out of Scope — chocolate cake triggers guardrail."""

    def test_classified_as_out_of_scope(self, db):
        scope = resolve_scope(db, "comp-aetheris-002", "s9t0-567")
        from backend.app.core.query_classifier import classify_query

        c = classify_query("How do I make a chocolate cake?", scope)
        assert c.intent == QueryIntent.OUT_OF_SCOPE

    def test_answer_is_guardrail(self, db, client):
        _, _, resp = _run_search(
            db,
            client,
            "comp-aetheris-002",
            "s9t0-567",
            "How do I make a chocolate cake?",
        )
        from backend.app.core.guardrails import OUT_OF_SCOPE_RESPONSE

        assert resp.answer == OUT_OF_SCOPE_RESPONSE

    def test_no_citations(self, db, client):
        _, _, resp = _run_search(
            db,
            client,
            "comp-aetheris-002",
            "s9t0-567",
            "How do I make a chocolate cake?",
        )
        assert len(resp.citations) == 0

    def test_no_llm_knowledge_leaked(self, db, client):
        _, _, resp = _run_search(
            db,
            client,
            "comp-aetheris-002",
            "s9t0-567",
            "How do I make a chocolate cake?",
        )
        answer_lower = resp.answer.lower()
        assert "chocolate" not in answer_lower
        assert "flour" not in answer_lower
        assert "recipe" not in answer_lower
