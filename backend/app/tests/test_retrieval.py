"""
Tests for chunk retrieval with scope-based filtering.

Includes:
  - Correctness tests (scope isolation, ranking)
  - Retrieval quality metrics (Precision@K, MRR)

All tests run against the real seeded database.
Key invariant: retrieval MUST never return chunks outside the user's scope.
"""

import pytest

from backend.app.core.scope_resolver import resolve_scope
from backend.app.db.session import SessionLocal
from backend.app.repositories.chunk_repo import ChunkResult, retrieve_chunks


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
def edward_scope(db):
    return resolve_scope(db, "comp-hexaloom-005", "e5f6-405")


@pytest.fixture()
def aaron_scope(db):
    return resolve_scope(db, "comp-veldra-001", "a1b2-401")


@pytest.fixture()
def daphne_scope(db):
    return resolve_scope(db, "comp-kyberon-003", "f2g3-580")


@pytest.fixture()
def clark_scope(db):
    return resolve_scope(db, "comp-sentivue-004", "s7f1-531")


@pytest.fixture()
def empty_scope(db):
    return resolve_scope(db, "comp-hexaloom-005", "h0s4-544")


# -----------------------------------------------------------------------
# Metric helpers
# -----------------------------------------------------------------------


def precision_at_k(results: list[ChunkResult], relevant_asset_ids: set[str], k: int) -> float:
    """Fraction of top-K results that come from a relevant asset.
    1.0 = all top-K are relevant, 0.0 = none are."""
    top_k = results[:k]
    if not top_k:
        return 0.0
    hits = sum(1 for r in top_k if r.asset_id in relevant_asset_ids)
    return hits / len(top_k)


def reciprocal_rank(results: list[ChunkResult], relevant_asset_ids: set[str]) -> float:
    """1/rank of the first relevant result. 1.0 = first result is relevant, 0.0 = none found."""
    for i, r in enumerate(results):
        if r.asset_id in relevant_asset_ids:
            return 1.0 / (i + 1)
    return 0.0


def mean_reciprocal_rank(
    queries: list[tuple[str, set[str]]],
    db,
    scope,
    limit: int = 10,
) -> float:
    """MRR across multiple (query, relevant_asset_ids) pairs."""
    rrs = []
    for query, relevant_ids in queries:
        results = retrieve_chunks(db, query, scope, limit=limit)
        rrs.append(reciprocal_rank(results, relevant_ids))
    return sum(rrs) / len(rrs) if rrs else 0.0


# -----------------------------------------------------------------------
# Basic retrieval
# -----------------------------------------------------------------------


class TestBasicRetrieval:
    def test_product_query_returns_results(self, db, frank_scope):
        results = retrieve_chunks(db, "Hexenon molecular structure", frank_scope)
        assert len(results) > 0

    def test_results_are_ranked(self, db, frank_scope):
        results = retrieve_chunks(db, "Hexenon", frank_scope)
        scores = [r.rank_score for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_results_contain_metadata(self, db, frank_scope):
        results = retrieve_chunks(db, "Hexenon", frank_scope)
        for r in results:
            assert r.chunk_id
            assert r.content
            assert r.company_id == "comp-hexaloom-005"
            assert r.metadata is not None

    def test_limit_is_respected(self, db, frank_scope):
        results = retrieve_chunks(db, "Hexenon", frank_scope, limit=3)
        assert len(results) <= 3

    def test_empty_scope_returns_nothing(self, db, empty_scope):
        results = retrieve_chunks(db, "Hexenon", empty_scope)
        assert len(results) == 0


# -----------------------------------------------------------------------
# Scope filtering — company isolation
# -----------------------------------------------------------------------


class TestCompanyIsolation:
    def test_frank_only_gets_hexaloom_chunks(self, db, frank_scope):
        results = retrieve_chunks(db, "product guide", frank_scope)
        for r in results:
            assert r.company_id == "comp-hexaloom-005"

    def test_aaron_only_gets_veldra_chunks(self, db, aaron_scope):
        results = retrieve_chunks(db, "product guide", aaron_scope)
        for r in results:
            assert r.company_id == "comp-veldra-001"

    def test_frank_cannot_retrieve_veldra_content(self, db, frank_scope):
        results = retrieve_chunks(db, "Amproxin antibiotic", frank_scope)
        for r in results:
            assert "amproxin" not in r.content.lower()


# -----------------------------------------------------------------------
# Scope filtering — asset isolation
# -----------------------------------------------------------------------


class TestAssetIsolation:
    def test_frank_only_gets_allowed_assets(self, db, frank_scope):
        results = retrieve_chunks(db, "Hexenon", frank_scope)
        for r in results:
            if r.source_type == "asset":
                assert r.asset_id in frank_scope.allowed_asset_ids

    def test_frank_cannot_see_play_hex_004_assets(self, db, frank_scope):
        results = retrieve_chunks(db, "ballistic absorption", frank_scope)
        for r in results:
            assert r.asset_id != "ast-hex-006"
            assert r.asset_id != "ast-hex-007"
            assert r.asset_id != "ast-hex-008"


# -----------------------------------------------------------------------
# Scope filtering — submission isolation
# -----------------------------------------------------------------------


class TestSubmissionIsolation:
    def test_frank_sees_own_submission_chunks(self, db, frank_scope):
        results = retrieve_chunks(db, "robotics changing", frank_scope)
        history_results = [r for r in results if r.source_type == "history"]
        for r in history_results:
            user_id = r.metadata.get("user_id")
            if user_id:
                assert user_id == "2c7i-106"

    def test_frank_cannot_see_edwards_submissions(self, db, frank_scope):
        results = retrieve_chunks(db, "technical points accurate", frank_scope)
        for r in results:
            if r.source_type == "history":
                assert r.metadata.get("user_id") != "e5f6-405"

    def test_edward_cannot_see_franks_submissions(self, db, edward_scope):
        results = retrieve_chunks(db, "changing robotics", edward_scope)
        for r in results:
            if r.source_type == "history":
                assert r.metadata.get("user_id") != "2c7i-106"

    def test_feedback_chunks_are_user_scoped(self, db, frank_scope):
        results = retrieve_chunks(db, "Feedback score", frank_scope)
        for r in results:
            if r.metadata.get("type") == "feedback":
                assert r.metadata.get("user_id") == "2c7i-106"


# -----------------------------------------------------------------------
# Precision@K — is the top-K dominated by the right source?
# -----------------------------------------------------------------------


class TestPrecisionAtK:
    """
    For each query, we define which asset(s) should ideally appear in top-K.
    Precision@K = (relevant in top K) / K.
    Threshold: P@3 >= 0.33 (at least 1 of top 3 is from the right asset).
    """

    def test_hexenon_structure_precision(self, db, frank_scope):
        """Query about Hexenon structure → should hit what_is_hexenon (ast-hex-001)."""
        results = retrieve_chunks(db, "Hexenon molecular structure carbon nanotube", frank_scope)
        p3 = precision_at_k(results, {"ast-hex-001"}, k=3)
        assert p3 >= 0.33, f"P@3={p3:.2f} — expected ast-hex-001 in top 3"

    def test_amproxin_eradication_precision(self, db, aaron_scope):
        """Eradication rate query → should hit amproxin_guide (ast-vel-001)."""
        results = retrieve_chunks(db, "eradication rate Streptococcus pneumoniae", aaron_scope)
        p3 = precision_at_k(results, {"ast-vel-001"}, k=3)
        assert p3 >= 0.33, f"P@3={p3:.2f} — expected ast-vel-001 in top 3"

    def test_gridmaster_thermal_precision(self, db, daphne_scope):
        """Rack temperature query → should hit gridmaster_blueprint (ast-kyb-001)."""
        results = retrieve_chunks(db, "rack temperature baseline thermal efficiency", daphne_scope)
        p3 = precision_at_k(results, {"ast-kyb-001"}, k=3)
        assert p3 >= 0.33, f"P@3={p3:.2f} — expected ast-kyb-001 in top 3"

    def test_sentilink_speed_precision(self, db, clark_scope):
        """Sentilink speed query → should hit sentilink_ai_speed (ast-sen-002)."""
        results = retrieve_chunks(db, "Sentilink acceleration speed insight", clark_scope)
        p3 = precision_at_k(results, {"ast-sen-002"}, k=3)
        assert p3 >= 0.33, f"P@3={p3:.2f} — expected ast-sen-002 in top 3"

    def test_cooling_costs_submission_precision(self, db, daphne_scope):
        """Cooling costs → should hit Daphne's submission (ast-sub-kyb-001)."""
        results = retrieve_chunks(db, "cooling costs 32 percent", daphne_scope)
        p3 = precision_at_k(results, {"ast-sub-kyb-001"}, k=3)
        assert p3 >= 0.33, f"P@3={p3:.2f} — expected ast-sub-kyb-001 in top 3"

    def test_fuzzy_typo_precision(self, db, clark_scope):
        """Typo 'Sentalink' → should still find sentilink asset."""
        results = retrieve_chunks(db, "Sentalink acceleration speed", clark_scope)
        p3 = precision_at_k(results, {"ast-sen-002"}, k=3)
        assert p3 >= 0.33, f"P@3={p3:.2f} — fuzzy match failed for Sentalink typo"


# -----------------------------------------------------------------------
# MRR — is the first relevant result ranked highly?
# -----------------------------------------------------------------------


class TestMRR:
    """
    Mean Reciprocal Rank across a batch of queries per user.
    MRR = average(1/rank_of_first_relevant) across queries.
    Threshold: MRR >= 0.5 (first relevant result is in top 2 on average).
    """

    def test_aaron_mrr(self, db, aaron_scope):
        """Aaron (Veldra/Amproxin) — queries about his training content."""
        queries = [
            ("What is Amproxin?", {"ast-vel-001"}),
            ("eradication rate pneumoniae", {"ast-vel-001"}),
            ("dosage sinusitis", {"ast-vel-002"}),
            ("adverse reactions nausea", {"ast-vel-002"}),
        ]
        mrr = mean_reciprocal_rank(queries, db, aaron_scope)
        assert mrr >= 0.5, f"Aaron MRR={mrr:.2f} — below 0.5 threshold"

    def test_daphne_mrr(self, db, daphne_scope):
        """Daphne (Kyberon/GridMaster) — training + submission queries."""
        queries = [
            ("GridMaster hardware specs processor", {"ast-kyb-001"}),
            ("thermal efficiency rack temperature", {"ast-kyb-001"}),
            ("cooling costs 32 percent", {"ast-sub-kyb-001"}),
            ("PUE power usage", {"ast-kyb-001"}),
        ]
        mrr = mean_reciprocal_rank(queries, db, daphne_scope)
        assert mrr >= 0.5, f"Daphne MRR={mrr:.2f} — below 0.5 threshold"

    def test_frank_mrr(self, db, frank_scope):
        """Frank (Hexaloom) — queries across his 3 assigned plays."""
        queries = [
            ("Hexenon molecular DNA carbon", {"ast-hex-001"}),
            ("Synthetic Sinew robotics muscle", {"ast-hex-002"}),
            ("non-toxic polymer standards", {"ast-hex-009"}),
            ("tensile strength comparison table", {"ast-hex-001"}),
        ]
        mrr = mean_reciprocal_rank(queries, db, frank_scope)
        assert mrr >= 0.5, f"Frank MRR={mrr:.2f} — below 0.5 threshold"

    def test_clark_mrr(self, db, clark_scope):
        """Clark (Sentivue/Sentilink) — including fuzzy queries."""
        queries = [
            ("Sentilink integration walkthrough", {"ast-sen-002"}),
            ("15x time to first insight", {"ast-sen-002"}),
            ("Sentalink speed", {"ast-sen-002"}),  # typo
            ("Vorex acceleration data feeding", {"ast-sen-002"}),
        ]
        mrr = mean_reciprocal_rank(queries, db, clark_scope)
        assert mrr >= 0.5, f"Clark MRR={mrr:.2f} — below 0.5 threshold"
