"""
Tests for ScopeResolver against the real seeded Postgres database.

Test users (from seeded data):
  - Frank White (2c7i-106) — Hexaloom, 3 play assignments, 2 submissions, 2 feedback
  - Aaron Montgomery (a1b2-401) — Veldra, 1 play assignment, 1 submission
  - Johnny Storm (h0s4-544) — Hexaloom, 0 assignments
  - Edward Norton (e5f6-405) — Hexaloom, 2 assignments, 2 submissions (peer of Frank)
"""

import pytest

from backend.app.core.scope_resolver import ScopeError, resolve_scope
from backend.app.db.session import SessionLocal


@pytest.fixture()
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


# -----------------------------------------------------------------------
# Happy path
# -----------------------------------------------------------------------


class TestHappyPath:
    def test_frank_gets_correct_plays(self, db):
        scope = resolve_scope(db, "comp-hexaloom-005", "2c7i-106")
        assert scope.allowed_play_ids == {
            "play-hex-001",
            "play-hex-002",
            "play-hex-005",
        }

    def test_frank_gets_watch_reps_only(self, db):
        scope = resolve_scope(db, "comp-hexaloom-005", "2c7i-106")
        # watch reps for plays 001, 002, 005
        assert "rep-hex-001" in scope.allowed_rep_ids  # watch, play-hex-001
        assert "rep-hex-003" in scope.allowed_rep_ids  # watch, play-hex-002
        assert "rep-hex-014" in scope.allowed_rep_ids  # watch, play-hex-005
        # practice reps must NOT appear
        assert "rep-hex-002" not in scope.allowed_rep_ids  # practice
        assert "rep-hex-004" not in scope.allowed_rep_ids  # practice
        assert "rep-hex-015" not in scope.allowed_rep_ids  # practice

    def test_frank_gets_training_assets(self, db):
        scope = resolve_scope(db, "comp-hexaloom-005", "2c7i-106")
        assert "ast-hex-001" in scope.allowed_asset_ids  # what_is_hexenon
        assert "ast-hex-002" in scope.allowed_asset_ids  # synthetic_sinew_demo
        assert "ast-hex-009" in scope.allowed_asset_ids  # non_toxic_polymer_standards

    def test_frank_gets_own_submissions(self, db):
        scope = resolve_scope(db, "comp-hexaloom-005", "2c7i-106")
        assert scope.allowed_submission_ids == {"sub-hex-001", "sub-hex-007"}

    def test_frank_gets_submission_assets(self, db):
        scope = resolve_scope(db, "comp-hexaloom-005", "2c7i-106")
        assert "ast-hex-sub-001" in scope.allowed_asset_ids
        assert "ast-hex-sub-007" in scope.allowed_asset_ids

    def test_frank_gets_own_feedback(self, db):
        scope = resolve_scope(db, "comp-hexaloom-005", "2c7i-106")
        # fb-hex-001 -> sub-hex-001 (Frank's), fb-hex-007 -> sub-hex-007 (Frank's)
        assert scope.allowed_feedback_ids == {"fb-hex-001", "fb-hex-007"}

    def test_user_with_no_assignments(self, db):
        scope = resolve_scope(db, "comp-hexaloom-005", "h0s4-544")  # Johnny Storm
        assert scope.allowed_play_ids == set()
        assert scope.allowed_rep_ids == set()
        assert scope.allowed_asset_ids == set()
        assert scope.allowed_submission_ids == set()
        assert scope.allowed_feedback_ids == set()
        assert scope.is_empty


# -----------------------------------------------------------------------
# Cross-company rejection
# -----------------------------------------------------------------------


class TestCrossCompanyRejection:
    def test_veldra_user_cannot_access_hexaloom(self, db):
        with pytest.raises(ScopeError, match="not comp-hexaloom-005"):
            resolve_scope(db, "comp-hexaloom-005", "a1b2-401")  # Aaron is Veldra

    def test_hexaloom_user_cannot_access_veldra(self, db):
        with pytest.raises(ScopeError, match="not comp-veldra-001"):
            resolve_scope(db, "comp-veldra-001", "2c7i-106")  # Frank is Hexaloom

    def test_nonexistent_user(self, db):
        with pytest.raises(ScopeError, match="not found"):
            resolve_scope(db, "comp-hexaloom-005", "does-not-exist")


# -----------------------------------------------------------------------
# Unassigned play exclusion
# -----------------------------------------------------------------------


class TestUnassignedPlayExclusion:
    def test_frank_cannot_see_unassigned_hex_plays(self, db):
        scope = resolve_scope(db, "comp-hexaloom-005", "2c7i-106")
        # Frank is assigned hex-001, hex-002, hex-005 only
        assert "play-hex-003" not in scope.allowed_play_ids
        assert "play-hex-004" not in scope.allowed_play_ids

    def test_frank_cannot_see_unassigned_play_assets(self, db):
        scope = resolve_scope(db, "comp-hexaloom-005", "2c7i-106")
        # Assets from play-hex-003 (surgical specs, neuro-linker, spinal bridge)
        assert "ast-hex-003" not in scope.allowed_asset_ids
        assert "ast-hex-004" not in scope.allowed_asset_ids
        assert "ast-hex-005" not in scope.allowed_asset_ids
        # Assets from play-hex-004 (ballistic, impact test, plating)
        assert "ast-hex-006" not in scope.allowed_asset_ids
        assert "ast-hex-007" not in scope.allowed_asset_ids
        assert "ast-hex-008" not in scope.allowed_asset_ids


# -----------------------------------------------------------------------
# Peer submission + feedback exclusion
# -----------------------------------------------------------------------


class TestPeerExclusion:
    def test_frank_cannot_see_edwards_submissions(self, db):
        scope = resolve_scope(db, "comp-hexaloom-005", "2c7i-106")
        assert "sub-hex-002" not in scope.allowed_submission_ids
        assert "sub-hex-008" not in scope.allowed_submission_ids

    def test_frank_cannot_see_peer_submission_assets(self, db):
        scope = resolve_scope(db, "comp-hexaloom-005", "2c7i-106")
        assert "ast-hex-sub-002" not in scope.allowed_asset_ids
        assert "ast-hex-sub-008" not in scope.allowed_asset_ids

    def test_frank_cannot_see_edwards_feedback(self, db):
        scope = resolve_scope(db, "comp-hexaloom-005", "2c7i-106")
        # fb-hex-002 -> sub-hex-002 (Edward's)
        assert "fb-hex-002" not in scope.allowed_feedback_ids

    def test_edward_cannot_see_franks_submissions(self, db):
        scope = resolve_scope(db, "comp-hexaloom-005", "e5f6-405")
        assert "sub-hex-001" not in scope.allowed_submission_ids
        assert "sub-hex-007" not in scope.allowed_submission_ids

    def test_edward_cannot_see_franks_feedback(self, db):
        scope = resolve_scope(db, "comp-hexaloom-005", "e5f6-405")
        assert "fb-hex-001" not in scope.allowed_feedback_ids
        assert "fb-hex-007" not in scope.allowed_feedback_ids

    def test_scopes_are_symmetric_on_shared_training_assets(self, db):
        frank = resolve_scope(db, "comp-hexaloom-005", "2c7i-106")
        edward = resolve_scope(db, "comp-hexaloom-005", "e5f6-405")
        # Both assigned hex-001, hex-002, hex-005 -> same training assets
        shared_training = {"ast-hex-001", "ast-hex-002", "ast-hex-009"}
        assert shared_training <= frank.allowed_asset_ids
        assert shared_training <= edward.allowed_asset_ids
        # But submissions and feedback are disjoint
        assert frank.allowed_submission_ids & edward.allowed_submission_ids == set()
        assert frank.allowed_feedback_ids & edward.allowed_feedback_ids == set()
