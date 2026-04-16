"""
ScopeResolver: determines exactly what a user is allowed to search.

This runs BEFORE any retrieval. The returned SearchScope is the
authorization boundary — vector search must be filtered to these IDs.

Resolution chain:
  1. Verify user belongs to the requested company
  2. play_assignments -> play_ids
  3. reps (watch only) for those plays -> rep_ids + asset_ids
  4. submissions WHERE user_id = user -> submission_ids + their asset_ids
  5. feedback WHERE submission_id in user's submissions -> feedback_ids
  6. Bundle into SearchScope
"""

from sqlalchemy.orm import Session

from backend.app.models.search import SearchScope
from backend.app.repositories.scope_repo import (
    get_assigned_play_ids,
    get_feedback_ids,
    get_play_titles,
    get_rep_asset_ids,
    get_submission_asset_ids,
    get_user_info,
    get_user_submission_ids,
    get_watch_rep_ids,
)


class ScopeError(Exception):
    """Raised when scope resolution fails due to authorization."""

    pass


def resolve_scope(db: Session, company_id: str, user_id: str) -> SearchScope:
    """
    Build the full authorization scope for a user within a company.
    Raises ScopeError if the user doesn't belong to the company.
    """
    # 1. Verify user belongs to the requested company
    user_info = get_user_info(db, user_id)
    if user_info is None:
        raise ScopeError(f"User {user_id} not found or inactive")
    actual_company, display_name = user_info
    if actual_company != company_id:
        raise ScopeError(f"User {user_id} belongs to {actual_company}, not {company_id}")

    # 2. Assigned plays
    play_ids = get_assigned_play_ids(db, user_id)

    # 3. Watch reps -> training assets
    rep_ids = get_watch_rep_ids(db, play_ids)
    training_asset_ids = get_rep_asset_ids(db, rep_ids)

    # 4. User's own submissions -> submission assets
    submission_ids = get_user_submission_ids(db, user_id)
    submission_asset_ids = get_submission_asset_ids(db, submission_ids)

    # 5. Feedback on user's submissions
    feedback_ids = get_feedback_ids(db, submission_ids)

    # 6. Play titles for classifier context
    play_title_list = get_play_titles(db, play_ids)

    # 7. Combine
    all_asset_ids = training_asset_ids | submission_asset_ids

    return SearchScope(
        company_id=company_id,
        user_id=user_id,
        allowed_play_ids=play_ids,
        allowed_rep_ids=rep_ids,
        allowed_asset_ids=all_asset_ids,
        allowed_submission_ids=submission_ids,
        allowed_feedback_ids=feedback_ids,
        play_titles=play_title_list,
        user_display_name=display_name,
    )
