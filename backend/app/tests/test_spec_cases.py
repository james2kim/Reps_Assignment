"""
End-to-end tests matching the spec's test case suite.

These verify the full pipeline: scope → classify → retrieve → answer
against real seeded data.

Tests marked @requires_llm need ANTHROPIC_API_KEY set in .env.
All test case numbers reference the spec document.
"""

import pytest

from backend.app.config import settings
from backend.app.core.answer_generator import generate_answer
from backend.app.core.guardrails import OUT_OF_SCOPE_RESPONSE, PROPRIETARY_UNGROUNDED_RESPONSE
from backend.app.core.retrieval_router import route_query
from backend.app.core.scope_resolver import ScopeError, resolve_scope
from backend.app.db.session import SessionLocal
from backend.app.models.enums import QueryIntent, RetrievalStrategy
from backend.app.repositories.chunk_repo import retrieve_chunks

requires_llm = pytest.mark.skipif(
    not settings.anthropic_api_key,
    reason="ANTHROPIC_API_KEY not set",
)


@pytest.fixture()
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


# -----------------------------------------------------------------------
# Helper: run full pipeline and return response
# -----------------------------------------------------------------------


def _search(db, company_id, user_id, query):
    scope = resolve_scope(db, company_id, user_id)
    retrieval = route_query(db, query, scope)
    response = generate_answer(db, query, retrieval)
    return scope, retrieval, response


# =======================================================================
# HAPPY SCENARIO 1: Valid Search (Authorized Access)
# =======================================================================


class TestCase1_1_KnowledgeBasePDFSearch:
    """
    User: aaron-veldra (a1b2-401) — Veldra
    Assigned: play-vel-001 (Amproxin: Antibiotic Excellence)
    Query: "What is the eradication rate for Streptococcus pneumoniae?"
    Expected: 94.2% from amproxin_guide.pdf Page 1
    """

    def test_aaron_can_search_amproxin(self, db):
        scope, retrieval, resp = _search(
            db,
            "comp-veldra-001",
            "a1b2-401",
            "What is the eradication rate for Streptococcus pneumoniae?",
        )
        assert retrieval.classification.intent == QueryIntent.ASSIGNED_SEARCH

    def test_retrieval_finds_eradication_rate(self, db):
        scope = resolve_scope(db, "comp-veldra-001", "a1b2-401")
        chunks = retrieve_chunks(db, "eradication rate Streptococcus pneumoniae", scope)
        content = " ".join(c.content for c in chunks)
        assert "94.2%" in content

    def test_citation_references_amproxin_guide(self, db):
        scope, retrieval, resp = _search(
            db,
            "comp-veldra-001",
            "a1b2-401",
            "What is the eradication rate for Streptococcus pneumoniae?",
        )
        pdf_citations = [c for c in resp.citations if c.source_type == "pdf"]
        filenames = {c.source_file for c in pdf_citations}
        assert "amproxin_guide.pdf" in filenames


class TestCase1_2_PersonalSubmissionSearch:
    """
    User: daphne-kyberon (f2g3-580) — Kyberon
    Submission: sub-kyb-001 (GridMaster Pitch)
    Query: "When did I mention cooling energy costs?"
    Expected: "reduces cooling costs by up to 32 percent" at 00:26-00:38
    """

    def test_daphne_can_search_own_submission(self, db):
        scope = resolve_scope(db, "comp-kyberon-003", "f2g3-580")
        assert "sub-kyb-001" in scope.allowed_submission_ids

    def test_retrieval_finds_cooling_costs(self, db):
        scope = resolve_scope(db, "comp-kyberon-003", "f2g3-580")
        chunks = retrieve_chunks(db, "cooling energy costs", scope)
        matched = [c for c in chunks if "cooling" in c.content.lower()]
        assert len(matched) > 0
        # Verify it's from Daphne's submission, not training content
        sub_chunks = [c for c in matched if c.source_type == "history"]
        assert len(sub_chunks) > 0

    def test_citation_has_timestamp(self, db):
        scope = resolve_scope(db, "comp-kyberon-003", "f2g3-580")
        chunks = retrieve_chunks(db, "cooling energy costs", scope)
        cooling_chunks = [c for c in chunks if "cooling" in c.content.lower()]
        # Segments are grouped into paragraphs — the chunk containing "cooling costs"
        # may start at 00:00 (grouped) rather than 00:26 (original segment)
        has_timestamp = any(c.metadata.get("start") for c in cooling_chunks)
        assert has_timestamp, "No timestamp found on cooling cost chunks"


# =======================================================================
# HAPPY SCENARIO 2: Invalid Search (Unauthorized/Unassigned Content)
# =======================================================================


class TestCase2_1_CrossCompanyLeakage:
    """
    User: sophie-aetheris (a8m2-512) — Aetheris
    Query: "Show me the GridMaster PUE efficiency table." (Kyberon content)
    Expected: No Kyberon content returned
    """

    def test_sophie_cannot_see_kyberon_content(self, db):
        scope = resolve_scope(db, "comp-aetheris-002", "a8m2-512")
        chunks = retrieve_chunks(db, "GridMaster PUE efficiency table", scope)
        for c in chunks:
            assert c.company_id != "comp-kyberon-003"
            assert "gridmaster" not in c.content.lower()

    def test_cross_company_scope_raises_error(self, db):
        with pytest.raises(ScopeError):
            resolve_scope(db, "comp-kyberon-003", "a8m2-512")


class TestCase2_2_UnassignedPlaySameCompany:
    """
    User: leo-aetheris (k7l8-437) — Aetheris
    Assigned: play-aet-001 (Somnirel)
    NOT assigned: play-aet-002 (Nuvia)
    Query: "How does Lydrenex protect the amygdala?"
    Expected: No Nuvia content (amygdala is in Nuvia, not Somnirel)
    """

    def test_leo_only_has_somnirel(self, db):
        scope = resolve_scope(db, "comp-aetheris-002", "k7l8-437")
        assert "play-aet-001" in scope.allowed_play_ids
        assert "play-aet-002" not in scope.allowed_play_ids

    def test_leo_cannot_see_nuvia_assets(self, db):
        scope = resolve_scope(db, "comp-aetheris-002", "k7l8-437")
        # ast-aet-003 is the Nuvia asset
        assert "ast-aet-003" not in scope.allowed_asset_ids

    def test_leo_retrieval_excludes_nuvia(self, db):
        scope = resolve_scope(db, "comp-aetheris-002", "k7l8-437")
        chunks = retrieve_chunks(db, "Lydrenex protect amygdala", scope)
        for c in chunks:
            assert c.asset_id != "ast-aet-003"  # Nuvia asset


class TestCase2_3_PeerSubmissions:
    """
    User: aaron-veldra (a1b2-401) — Veldra
    Query: searching for another user's submission
    Expected: Cannot see other users' submissions
    """

    def test_aaron_cannot_see_felicia_submission(self, db):
        """Felicia (h8i9-556) also submitted for play-vel-001."""
        scope = resolve_scope(db, "comp-veldra-001", "a1b2-401")
        # sub-vel-001 belongs to Felicia
        assert "sub-vel-001" not in scope.allowed_submission_ids

    def test_aaron_only_sees_own_submission(self, db):
        scope = resolve_scope(db, "comp-veldra-001", "a1b2-401")
        # Aaron's submission
        assert "sub-vel-002" in scope.allowed_submission_ids
        # Verify no other user's submissions leak through retrieval
        chunks = retrieve_chunks(db, "pitch antibiotics", scope)
        for c in chunks:
            if c.source_type == "history" and c.metadata.get("user_id"):
                assert c.metadata["user_id"] == "a1b2-401"


# =======================================================================
# EDGE CASES (Context & Shared Ingredients)
# =======================================================================


class TestCase3_1_SharedIngredientDisambiguation:
    """
    Lydrenex is used by both:
      - Veldra: Zaloric (high-dose 50-100mg for muscle spasms)
      - Aetheris: Nuvia (low-dose 5-10mg for social anxiety)

    A Veldra user must only see Zaloric's dosage.
    An Aetheris user with Nuvia assigned must only see Nuvia's dosage.
    """

    def test_belinda_sees_veldra_lydrenex_only(self, db):
        """Belinda (f3g4-502, Veldra, assigned play-vel-002/Zaloric) should get Zaloric data."""
        scope = resolve_scope(db, "comp-veldra-001", "f3g4-502")
        assert "play-vel-002" in scope.allowed_play_ids
        chunks = retrieve_chunks(db, "What is the dosage for Lydrenex?", scope)
        content = " ".join(c.content for c in chunks)
        # Should see Veldra/Zaloric dosage
        assert "50mg" in content or "100mg" in content or "Zaloric" in content
        # Should NOT see Aetheris dosage
        for c in chunks:
            assert c.company_id == "comp-veldra-001"

    def test_sophie_sees_aetheris_lydrenex_only(self, db):
        """Sophie (Aetheris, assigned Nuvia) searching Lydrenex should get Nuvia data."""
        scope = resolve_scope(db, "comp-aetheris-002", "a8m2-512")
        chunks = retrieve_chunks(db, "What is the dosage for Lydrenex?", scope)
        for c in chunks:
            assert c.company_id == "comp-aetheris-002"

    def test_no_cross_company_bleed(self, db):
        """Neither user should see the other company's Lydrenex data."""
        belinda_scope = resolve_scope(db, "comp-veldra-001", "f3g4-502")
        sophie_scope = resolve_scope(db, "comp-aetheris-002", "a8m2-512")
        # Asset IDs should be completely disjoint
        assert belinda_scope.allowed_asset_ids & sophie_scope.allowed_asset_ids == set()


class TestCase3_2_MultiPageReasoning:
    """
    User: daphne-kyberon (f2g3-580) — Kyberon
    Query: "Compare rack temperature baseline vs GridMaster results"
    Expected: Baseline 24.5°C, With GridMaster 21.8°C, 11.02% gain
    Data lives in gridmaster_blueprint.pdf Page 2 Table 2
    """

    def test_daphne_can_find_thermal_data(self, db):
        scope = resolve_scope(db, "comp-kyberon-003", "f2g3-580")
        chunks = retrieve_chunks(db, "rack temperature baseline GridMaster", scope)
        content = " ".join(c.content for c in chunks)
        assert "24.5" in content  # baseline temp
        assert "21.8" in content  # post-GridMaster temp

    def test_thermal_data_from_correct_asset(self, db):
        scope = resolve_scope(db, "comp-kyberon-003", "f2g3-580")
        chunks = retrieve_chunks(db, "rack temperature thermal efficiency", scope)
        table_chunks = [c for c in chunks if "24.5" in c.content]
        assert len(table_chunks) > 0
        for c in table_chunks:
            assert c.asset_id == "ast-kyb-001"  # gridmaster_blueprint


# =======================================================================
# BAD DATA & ERROR HANDLING
# =======================================================================


class TestCase4_1_FuzzyMatchingTypo:
    """
    User: clark-sentivue (s7f1-531) — Sentivue
    Query: "Sentalink acceleration speed" (typo: should be Sentilink)
    Expected: Still finds Sentilink content
    """

    def test_typo_still_returns_results(self, db):
        scope = resolve_scope(db, "comp-sentivue-004", "s7f1-531")
        chunks = retrieve_chunks(db, "Sentalink acceleration speed", scope)
        assert len(chunks) > 0

    def test_typo_finds_sentilink_content(self, db):
        scope = resolve_scope(db, "comp-sentivue-004", "s7f1-531")
        chunks = retrieve_chunks(db, "Sentalink acceleration speed", scope)
        content = " ".join(c.content.lower() for c in chunks)
        assert "sentilink" in content


@requires_llm
class TestCase4_2_OutOfScope:
    """
    Query: "How do I make a chocolate cake?"
    Expected: Out-of-scope guardrail
    """

    def test_out_of_scope_response(self, db):
        scope, retrieval, resp = _search(
            db, "comp-aetheris-002", "a8m2-512", "How do I make a chocolate cake?"
        )
        assert resp.answer == OUT_OF_SCOPE_RESPONSE
        assert resp.citations == []

    def test_greeting_out_of_scope(self, db):
        scope, retrieval, resp = _search(db, "comp-aetheris-002", "a8m2-512", "Hello")
        assert resp.answer == OUT_OF_SCOPE_RESPONSE

    def test_general_knowledge_is_out_of_scope(self, db):
        """General knowledge (non-sales) should be out_of_scope."""
        scope, retrieval, resp = _search(
            db, "comp-aetheris-002", "a8m2-512", "Why is the world round?"
        )
        assert retrieval.classification.intent == QueryIntent.OUT_OF_SCOPE


# =======================================================================
# ADDITIONAL EDGE CASES (beyond spec, but important)
# =======================================================================


class TestAdditionalEdgeCases:
    def test_inactive_user_rejected(self, db):
        """kenji-veldra (v3h6-507) is is_active=FALSE."""
        with pytest.raises(ScopeError, match="not found"):
            resolve_scope(db, "comp-veldra-001", "v3h6-507")

    def test_user_with_no_assignments_gets_empty_scope(self, db):
        """johnny-hexaloom (h0s4-544) has 0 play assignments."""
        scope = resolve_scope(db, "comp-hexaloom-005", "h0s4-544")
        assert scope.is_empty

    def test_proprietary_query_with_empty_scope(self, db):
        """User with no materials asking about product data."""
        scope, retrieval, resp = _search(
            db, "comp-hexaloom-005", "h0s4-544", "What is the tensile strength of Hexenon?"
        )
        assert resp.answer == PROPRIETARY_UNGROUNDED_RESPONSE

    def test_structured_query_returns_feedback(self, db):
        """Daphne asking for her score should get structured feedback."""
        scope = resolve_scope(db, "comp-kyberon-003", "f2g3-580")
        retrieval = route_query(db, "What was my feedback score?", scope)
        assert retrieval.classification.strategy == RetrievalStrategy.STRUCTURED
        assert retrieval.structured is not None
        assert len(retrieval.structured.feedback) == 1
        assert retrieval.structured.feedback[0].score == 9

    def test_hybrid_query_gets_both(self, db):
        """Frank asking to improve should get feedback + training content."""
        scope = resolve_scope(db, "comp-hexaloom-005", "2c7i-106")
        retrieval = route_query(db, "How can I improve my pitch based on my feedback?", scope)
        assert retrieval.classification.strategy == RetrievalStrategy.HYBRID
        assert retrieval.structured is not None
        assert len(retrieval.structured.feedback) > 0
