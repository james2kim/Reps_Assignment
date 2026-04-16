"""
Structured lookups against relational tables.

These return facts (scores, statuses, lists) — not document content.
All queries are pre-filtered by the user's SearchScope.
"""

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.app.models.search import SearchScope


class PlayInfo(BaseModel):
    play_id: str
    title: str
    status: str


class SubmissionInfo(BaseModel):
    submission_id: str
    rep_title: str
    play_title: str
    submitted_at: str
    submission_type: str


class FeedbackInfo(BaseModel):
    feedback_id: str
    submission_id: str
    rep_title: str
    score: int
    text: str


class StructuredResult(BaseModel):
    """Container for all structured data relevant to a query."""

    plays: list[PlayInfo] = []
    submissions: list[SubmissionInfo] = []
    feedback: list[FeedbackInfo] = []

    @property
    def is_empty(self) -> bool:
        return not self.plays and not self.submissions and not self.feedback


def get_user_plays(db: Session, scope: SearchScope) -> list[PlayInfo]:
    """Assigned plays with their current status."""
    if not scope.allowed_play_ids:
        return []
    rows = db.execute(
        text(
            "SELECT p.id, p.title, pa.status "
            "FROM play_assignments pa "
            "JOIN plays p ON p.id = pa.play_id "
            "WHERE pa.user_id = :uid AND pa.play_id = ANY(:pids) "
            "ORDER BY pa.assigned_date DESC"
        ),
        {"uid": scope.user_id, "pids": list(scope.allowed_play_ids)},
    ).all()
    return [PlayInfo(play_id=r[0], title=r[1], status=r[2]) for r in rows]


def get_user_submissions(db: Session, scope: SearchScope) -> list[SubmissionInfo]:
    """User's own submissions with rep and play context."""
    if not scope.allowed_submission_ids:
        return []
    rows = db.execute(
        text(
            "SELECT s.id, r.prompt_title, p.title, s.submitted_at, s.submission_type "
            "FROM submissions s "
            "JOIN reps r ON r.id = s.rep_id "
            "JOIN plays p ON p.id = r.play_id "
            "WHERE s.id = ANY(:sids) "
            "ORDER BY s.submitted_at DESC"
        ),
        {"sids": list(scope.allowed_submission_ids)},
    ).all()
    return [
        SubmissionInfo(
            submission_id=r[0],
            rep_title=r[1],
            play_title=r[2],
            submitted_at=str(r[3]),
            submission_type=r[4],
        )
        for r in rows
    ]


def get_user_feedback(db: Session, scope: SearchScope) -> list[FeedbackInfo]:
    """Feedback on the user's own submissions."""
    if not scope.allowed_feedback_ids:
        return []
    rows = db.execute(
        text(
            "SELECT f.id, f.submission_id, r.prompt_title, f.score, f.text "
            "FROM feedback f "
            "JOIN submissions s ON s.id = f.submission_id "
            "JOIN reps r ON r.id = s.rep_id "
            "WHERE f.id = ANY(:fids) "
            "ORDER BY f.score DESC"
        ),
        {"fids": list(scope.allowed_feedback_ids)},
    ).all()
    return [
        FeedbackInfo(
            feedback_id=r[0],
            submission_id=r[1],
            rep_title=r[2],
            score=r[3],
            text=r[4],
        )
        for r in rows
    ]


def structured_lookup(db: Session, scope: SearchScope) -> StructuredResult:
    """Fetch all structured data for the user's scope."""
    return StructuredResult(
        plays=get_user_plays(db, scope),
        submissions=get_user_submissions(db, scope),
        feedback=get_user_feedback(db, scope),
    )
