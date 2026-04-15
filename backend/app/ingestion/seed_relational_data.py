"""
Seed Postgres from the CSV/JSON files in data/database/.

Insertion order respects foreign keys:
  1. companies   (no deps)
  2. users       (-> companies)
  3. plays       (-> companies)
  4. assets      (-> companies)
  5. play_assignments (-> users, plays)
  6. reps        (-> plays, companies, assets)
  7. submissions (-> users, reps, assets, companies)
  8. feedback    (-> submissions, companies)

Source data has orphan references (e.g. user j0i9-305, plays hex-006..010,
rep-hex-024). Rows referencing missing FKs are skipped with a warning.
"""

import csv
import json
from datetime import datetime
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.app.config import settings
from backend.app.db.session import SessionLocal

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

DATA_DIR = settings.database_dir

FILE_MAP = {
    "companies": "BigSpring_takehome_data - comapny.json",  # typo in source
    "users": "BigSpring_takehome_data - users.csv",
    "plays": "BigSpring_takehome_data - play.csv",
    "assets": "BigSpring_takehome_data - asset.csv",
    "play_assignments": "BigSpring_takehome_data - play_assignment.csv",
    "reps": "BigSpring_takehome_data - rep.csv",
    "submissions": "BigSpring_takehome_data - submission.csv",
    "feedback": "BigSpring_takehome_data - feedback.csv",
}

# Populated during seeding so downstream parsers can skip orphan rows
_known_ids: dict[str, set[str]] = {}


def _path(key: str) -> Path:
    return DATA_DIR / FILE_MAP[key]


def _parse_bool(val: str) -> bool:
    return val.strip().upper() == "TRUE"


def _parse_ts(val: str) -> datetime | None:
    val = val.strip()
    if not val:
        return None
    return datetime.fromisoformat(val.replace("Z", "+00:00"))


def _parse_int(val: str) -> int:
    return int(val.strip())


def _nullable_str(val: str) -> str | None:
    val = val.strip()
    return val if val else None


def _read_csv(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _register(table: str, rows: list[dict]) -> list[dict]:
    """Track inserted IDs so downstream parsers can validate FK refs."""
    _known_ids[table] = {r["id"] for r in rows}
    return rows


def _has_ref(row: dict, col: str, table: str) -> bool:
    """Return True if the FK value exists (or is NULL for nullable cols)."""
    val = row.get(col)
    if val is None:
        return True  # nullable FK
    return val in _known_ids.get(table, set())


# ---------------------------------------------------------------------------
# Parsers — one per table, returns list of row-dicts ready for INSERT
# ---------------------------------------------------------------------------


def parse_companies() -> list[dict]:
    with open(_path("companies"), encoding="utf-8") as f:
        data = json.load(f)
    rows = [
        {"id": c["id"], "name": c["name"], "description": c.get("description", "")}
        for c in data["companies"]
    ]
    return _register("companies", rows)


def parse_users() -> list[dict]:
    rows = _read_csv(_path("users"))
    parsed = [
        {
            "id": r["id"],
            "username": r["username"],
            "display_name": r["display_name"],
            "role": r["role"],
            "segment": r["segment"],
            "created_at": _parse_ts(r["created_at"]),
            "is_active": _parse_bool(r["is_active"]),
            "company_id": r["company_id"],
        }
        for r in rows
    ]
    return _register("users", parsed)


def parse_plays() -> list[dict]:
    rows = _read_csv(_path("plays"))
    parsed = [
        {
            "id": r["id"],
            "company_id": r["company_id"],
            "title": r["title"],
            "description": r["description"],
            "created_at": _parse_ts(r["created_at"]),
            "is_active": _parse_bool(r["is_active"]),
        }
        for r in rows
    ]
    return _register("plays", parsed)


def parse_assets() -> list[dict]:
    rows = _read_csv(_path("assets"))
    parsed = [
        {
            "id": r["id"],
            "type": r["type"],
            "file_name": r["file_name"],
            "created_at": _parse_ts(r["created_at"]),
            "company_id": r["company_id"],
        }
        for r in rows
    ]
    return _register("assets", parsed)


def parse_play_assignments() -> list[dict]:
    rows = _read_csv(_path("play_assignments"))
    parsed = []
    skipped = 0
    for r in rows:
        row = {
            "id": r["id"],
            "user_id": r["user_id"],
            "play_id": r["play_id"],
            "assigned_date": _parse_ts(r["assigned_date"]),
            "status": r["status"],
            "completed_at": _parse_ts(r["completed_at"]),
        }
        if _has_ref(row, "user_id", "users") and _has_ref(row, "play_id", "plays"):
            parsed.append(row)
        else:
            skipped += 1
    if skipped:
        print(f"    ⚠ play_assignments: skipped {skipped} rows (missing user/play FK)")
    return _register("play_assignments", parsed)


def parse_reps() -> list[dict]:
    rows = _read_csv(_path("reps"))
    parsed = []
    skipped = 0
    for r in rows:
        row = {
            "id": r["id"],
            "prompt_text": r["prompt_text"],
            "prompt_title": r["prompt_title"],
            "prompt_type": r["prompt_type"],
            "play_id": r["play_id"],
            "company_id": r["company_id"],
            "asset_id": _nullable_str(r["asset_id"]),
            "created_at": _parse_ts(r["created_at"]),
        }
        if _has_ref(row, "play_id", "plays") and _has_ref(row, "asset_id", "assets"):
            parsed.append(row)
        else:
            skipped += 1
    if skipped:
        print(f"    ⚠ reps: skipped {skipped} rows (missing play/asset FK)")
    return _register("reps", parsed)


def parse_submissions() -> list[dict]:
    rows = _read_csv(_path("submissions"))
    parsed = []
    skipped = 0
    for r in rows:
        row = {
            "id": r["id"],
            "user_id": r["user_id"],
            "rep_id": r["rep_id"],
            "submitted_at": _parse_ts(r["submitted_at"]),
            "submission_type": r["submission_type"],
            "asset_id": r["asset_id"],
            "company_id": r["company_id"],
        }
        if (
            _has_ref(row, "user_id", "users")
            and _has_ref(row, "rep_id", "reps")
            and _has_ref(row, "asset_id", "assets")
        ):
            parsed.append(row)
        else:
            skipped += 1
    if skipped:
        print(f"    ⚠ submissions: skipped {skipped} rows (missing user/rep/asset FK)")
    return _register("submissions", parsed)


def parse_feedback() -> list[dict]:
    rows = _read_csv(_path("feedback"))
    parsed = []
    skipped = 0
    for r in rows:
        row = {
            "id": r["id"],
            "submission_id": r["submission_id"],
            "company_id": r["company_id"],
            "score": _parse_int(r["score"]),
            "text": r["text"],
            "created_at": _parse_ts(r["created_at"]),
        }
        if _has_ref(row, "submission_id", "submissions"):
            parsed.append(row)
        else:
            skipped += 1
    if skipped:
        print(f"    ⚠ feedback: skipped {skipped} rows (missing submission FK)")
    return _register("feedback", parsed)


# ---------------------------------------------------------------------------
# Insertion
# ---------------------------------------------------------------------------

SEED_STEPS: list[tuple[str, callable]] = [
    ("companies", parse_companies),
    ("users", parse_users),
    ("plays", parse_plays),
    ("assets", parse_assets),
    ("play_assignments", parse_play_assignments),
    ("reps", parse_reps),
    ("submissions", parse_submissions),
    ("feedback", parse_feedback),
]

# Reverse order for safe truncation
TABLES = [t for t, _ in SEED_STEPS]


def _bulk_insert(db: Session, table: str, rows: list[dict]) -> int:
    if not rows:
        return 0
    cols = list(rows[0].keys())
    placeholders = ", ".join(f":{c}" for c in cols)
    col_names = ", ".join(cols)
    stmt = text(f"INSERT INTO {table} ({col_names}) VALUES ({placeholders})")
    db.execute(stmt, rows)
    return len(rows)


def _truncate_all(db: Session) -> None:
    """Clear all tables in reverse FK order."""
    for table in reversed(TABLES):
        db.execute(text(f"DELETE FROM {table}"))
    # Also clear search_chunks if it exists
    db.execute(text("DELETE FROM search_chunks"))


def seed(db: Session | None = None) -> dict[str, int]:
    """Run all seed steps. Returns {table: row_count}."""
    own_session = db is None
    if own_session:
        db = SessionLocal()

    try:
        print("  Clearing existing data...")
        _truncate_all(db)

        counts = {}
        for table, parser in SEED_STEPS:
            rows = parser()
            n = _bulk_insert(db, table, rows)
            counts[table] = n
            print(f"  {table}: {n} rows")
        db.commit()
        print("Seed complete.")
        return counts
    except Exception:
        db.rollback()
        raise
    finally:
        if own_session:
            db.close()


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("Seeding database...")
    seed()
