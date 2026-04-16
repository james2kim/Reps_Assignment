"""
Build search_chunks rows from assets, submissions, and feedback.

Three source types:
  - "asset"   → training content from watch reps (PDFs, videos, images)
  - "history" → user's own submission transcripts + feedback text

Writes directly to search_chunks via bulk INSERT.
"""

import json
import uuid

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.app.config import settings
from backend.app.db.session import SessionLocal
from backend.app.ingestion.parse_assets import parse_asset


def _new_id() -> str:
    return f"chunk-{uuid.uuid4().hex[:12]}"


def _json(obj: dict) -> str:
    return json.dumps(obj, default=str)


# ---------------------------------------------------------------------------
# 1. Training asset chunks (source_type = "asset")
# ---------------------------------------------------------------------------


def _build_asset_chunks(db: Session) -> list[dict]:
    """Chunks from watch-rep training assets (PDFs, videos, images)."""
    # Build lookup: asset_id -> context from reps
    rep_rows = db.execute(
        text(
            "SELECT r.asset_id, r.company_id, r.play_id, r.id as rep_id "
            "FROM reps r WHERE r.asset_id IS NOT NULL"
        )
    ).all()
    rep_context = {}
    for asset_id, company_id, play_id, rep_id in rep_rows:
        rep_context[asset_id] = {
            "company_id": company_id,
            "play_id": play_id,
            "rep_id": rep_id,
        }

    assets = db.execute(text("SELECT id, type, file_name FROM assets")).all()
    assets_dir = settings.assets_dir
    rows = []

    for asset_id, asset_type, file_name in assets:
        ctx = rep_context.get(asset_id)
        if not ctx:
            continue  # not a training asset (submission assets handled separately)

        path = assets_dir / file_name
        if not path.exists():
            print(f"  ⚠ Missing file: {file_name}, skipping")
            continue

        for chunk in parse_asset(asset_type, path):
            meta = chunk["metadata"]
            meta["play_id"] = ctx["play_id"]
            meta["rep_id"] = ctx["rep_id"]
            rows.append(
                {
                    "id": _new_id(),
                    "content": chunk["content"],
                    "source_type": "asset",
                    "source_id": asset_id,
                    "company_id": ctx["company_id"],
                    "asset_id": asset_id,
                    "metadata": _json(meta),
                }
            )

    return rows


# ---------------------------------------------------------------------------
# 2. Submission transcript chunks (source_type = "history")
# ---------------------------------------------------------------------------


def _build_submission_chunks(db: Session) -> list[dict]:
    """Chunks from user submission transcripts/text."""
    sub_rows = db.execute(
        text(
            "SELECT s.id, s.user_id, s.company_id, s.rep_id, s.asset_id, "
            "       s.submission_type, a.file_name, r.play_id "
            "FROM submissions s "
            "JOIN assets a ON a.id = s.asset_id "
            "JOIN reps r ON r.id = s.rep_id"
        )
    ).all()

    assets_dir = settings.assets_dir
    rows = []

    for (
        sub_id,
        user_id,
        company_id,
        rep_id,
        asset_id,
        sub_type,
        file_name,
        play_id,
    ) in sub_rows:
        path = assets_dir / file_name
        if not path.exists():
            print(f"  ⚠ Missing submission file: {file_name}, skipping")
            continue

        for chunk in parse_asset(sub_type, path):
            meta = chunk["metadata"]
            meta["user_id"] = user_id
            meta["submission_id"] = sub_id
            meta["rep_id"] = rep_id
            meta["play_id"] = play_id
            rows.append(
                {
                    "id": _new_id(),
                    "content": chunk["content"],
                    "source_type": "history",
                    "source_id": sub_id,
                    "company_id": company_id,
                    "asset_id": asset_id,
                    "metadata": _json(meta),
                }
            )

    return rows


# ---------------------------------------------------------------------------
# 3. Feedback chunks (source_type = "history")
# ---------------------------------------------------------------------------


def _build_feedback_chunks(db: Session) -> list[dict]:
    """One chunk per feedback entry, tied to the user who owns the submission."""
    fb_rows = db.execute(
        text(
            "SELECT f.id, f.submission_id, f.company_id, f.score, f.text, "
            "       s.user_id, s.rep_id, s.asset_id, r.play_id "
            "FROM feedback f "
            "JOIN submissions s ON s.id = f.submission_id "
            "JOIN reps r ON r.id = s.rep_id"
        )
    ).all()

    rows = []
    for (
        fb_id,
        sub_id,
        company_id,
        score,
        fb_text,
        user_id,
        rep_id,
        asset_id,
        play_id,
    ) in fb_rows:
        if not fb_text.strip():
            continue

        content = f"Feedback (score {score}/10): {fb_text.strip()}"
        meta = {
            "type": "feedback",
            "feedback_id": fb_id,
            "submission_id": sub_id,
            "user_id": user_id,
            "rep_id": rep_id,
            "play_id": play_id,
            "score": score,
        }
        rows.append(
            {
                "id": _new_id(),
                "content": content,
                "source_type": "history",
                "source_id": fb_id,
                "company_id": company_id,
                "asset_id": asset_id,
                "metadata": _json(meta),
            }
        )

    return rows


# ---------------------------------------------------------------------------
# Insertion
# ---------------------------------------------------------------------------


def _bulk_insert(db: Session, rows: list[dict]) -> int:
    if not rows:
        return 0
    stmt = text(
        "INSERT INTO search_chunks (id, content, source_type, source_id, company_id, asset_id, metadata) "
        "VALUES (:id, :content, :source_type, :source_id, :company_id, :asset_id, CAST(:metadata AS jsonb))"
    )
    db.execute(stmt, rows)
    return len(rows)


def build_and_insert(db: Session | None = None) -> int:
    """Main entry point. Returns total chunks inserted."""
    own_session = db is None
    if own_session:
        db = SessionLocal()

    try:
        db.execute(text("DELETE FROM search_chunks"))
        print("  Cleared existing chunks.")

        asset_rows = _build_asset_chunks(db)
        sub_rows = _build_submission_chunks(db)
        fb_rows = _build_feedback_chunks(db)

        all_rows = asset_rows + sub_rows + fb_rows
        n = _bulk_insert(db, all_rows)
        db.commit()

        print(f"  asset chunks:      {len(asset_rows)}")
        print(f"  submission chunks: {len(sub_rows)}")
        print(f"  feedback chunks:   {len(fb_rows)}")
        print(f"  total:             {n}")
        return n
    except Exception:
        db.rollback()
        raise
    finally:
        if own_session:
            db.close()


if __name__ == "__main__":
    print("Building and inserting search chunks...")
    build_and_insert()
