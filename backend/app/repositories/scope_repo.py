"""
Raw SQL queries for scope resolution. Each function returns a set of IDs.
Kept separate from business logic so queries are easy to read and test.
"""

from sqlalchemy import text
from sqlalchemy.orm import Session


def get_user_info(db: Session, user_id: str) -> tuple[str, str] | None:
    """Return (company_id, display_name) for a user, or None if not found."""
    row = db.execute(
        text("SELECT company_id, display_name FROM users WHERE id = :uid AND is_active = true"),
        {"uid": user_id},
    ).first()
    return (row[0], row[1]) if row else None


def get_assigned_play_ids(db: Session, user_id: str) -> set[str]:
    """Play IDs the user has been assigned to (any status)."""
    rows = db.execute(
        text("SELECT DISTINCT play_id FROM play_assignments WHERE user_id = :uid"),
        {"uid": user_id},
    ).all()
    return {r[0] for r in rows}


def get_watch_rep_ids(db: Session, play_ids: set[str]) -> set[str]:
    """Rep IDs of type 'watch' for the given plays."""
    if not play_ids:
        return set()
    rows = db.execute(
        text("SELECT id FROM reps WHERE play_id = ANY(:pids) AND prompt_type = 'watch'"),
        {"pids": list(play_ids)},
    ).all()
    return {r[0] for r in rows}


def get_rep_asset_ids(db: Session, rep_ids: set[str]) -> set[str]:
    """Asset IDs linked to the given reps (non-null only)."""
    if not rep_ids:
        return set()
    rows = db.execute(
        text("SELECT DISTINCT asset_id FROM reps WHERE id = ANY(:rids) AND asset_id IS NOT NULL"),
        {"rids": list(rep_ids)},
    ).all()
    return {r[0] for r in rows}


def get_user_submission_ids(db: Session, user_id: str) -> set[str]:
    """Submission IDs belonging to this user only."""
    rows = db.execute(
        text("SELECT id FROM submissions WHERE user_id = :uid"),
        {"uid": user_id},
    ).all()
    return {r[0] for r in rows}


def get_submission_asset_ids(db: Session, submission_ids: set[str]) -> set[str]:
    """Asset IDs linked to the given submissions."""
    if not submission_ids:
        return set()
    rows = db.execute(
        text("SELECT DISTINCT asset_id FROM submissions WHERE id = ANY(:sids)"),
        {"sids": list(submission_ids)},
    ).all()
    return {r[0] for r in rows}


def get_feedback_ids(db: Session, submission_ids: set[str]) -> set[str]:
    """Feedback IDs for the given submissions."""
    if not submission_ids:
        return set()
    rows = db.execute(
        text("SELECT id FROM feedback WHERE submission_id = ANY(:sids)"),
        {"sids": list(submission_ids)},
    ).all()
    return {r[0] for r in rows}


def get_play_titles(db: Session, play_ids: set[str]) -> list[str]:
    """Play titles for the given play IDs."""
    if not play_ids:
        return []
    rows = db.execute(
        text("SELECT title FROM plays WHERE id = ANY(:pids) ORDER BY title"),
        {"pids": list(play_ids)},
    ).all()
    return [r[0] for r in rows]
