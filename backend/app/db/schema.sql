-- All PKs are TEXT to match the source CSV IDs (e.g. "comp-veldra-001", "a1b2-401").
-- This avoids ID translation during seeding.

CREATE TABLE companies (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT ''
);

CREATE TABLE users (
    id           TEXT PRIMARY KEY,
    username     TEXT NOT NULL,
    display_name TEXT NOT NULL,
    role         TEXT NOT NULL,
    segment      TEXT NOT NULL DEFAULT '',
    created_at   TIMESTAMPTZ NOT NULL,
    is_active    BOOLEAN NOT NULL DEFAULT TRUE,
    company_id   TEXT NOT NULL REFERENCES companies(id)
);
CREATE INDEX idx_users_company ON users(company_id);

CREATE TABLE plays (
    id          TEXT PRIMARY KEY,
    company_id  TEXT NOT NULL REFERENCES companies(id),
    title       TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    created_at  TIMESTAMPTZ NOT NULL,
    is_active   BOOLEAN NOT NULL DEFAULT TRUE
);
CREATE INDEX idx_plays_company ON plays(company_id);

CREATE TABLE play_assignments (
    id            TEXT PRIMARY KEY,
    user_id       TEXT NOT NULL REFERENCES users(id),
    play_id       TEXT NOT NULL REFERENCES plays(id),
    assigned_date TIMESTAMPTZ NOT NULL,
    status        TEXT NOT NULL DEFAULT 'assigned',
    completed_at  TIMESTAMPTZ
);
CREATE INDEX idx_play_assignments_user ON play_assignments(user_id);
CREATE INDEX idx_play_assignments_play ON play_assignments(play_id);

CREATE TABLE assets (
    id         TEXT PRIMARY KEY,
    type       TEXT NOT NULL,
    file_name  TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    company_id TEXT NOT NULL REFERENCES companies(id)
);
CREATE INDEX idx_assets_company ON assets(company_id);

CREATE TABLE reps (
    id           TEXT PRIMARY KEY,
    prompt_text  TEXT NOT NULL,
    prompt_title TEXT NOT NULL,
    prompt_type  TEXT NOT NULL,       -- 'watch' | 'practice'
    play_id      TEXT NOT NULL REFERENCES plays(id),
    company_id   TEXT NOT NULL REFERENCES companies(id),
    asset_id     TEXT REFERENCES assets(id),  -- NULL for practice reps
    created_at   TIMESTAMPTZ NOT NULL
);
CREATE INDEX idx_reps_play ON reps(play_id);
CREATE INDEX idx_reps_asset ON reps(asset_id);

CREATE TABLE submissions (
    id              TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL REFERENCES users(id),
    rep_id          TEXT NOT NULL REFERENCES reps(id),
    submitted_at    TIMESTAMPTZ NOT NULL,
    submission_type TEXT NOT NULL,    -- 'video' | 'audio' | 'text'
    asset_id        TEXT NOT NULL REFERENCES assets(id),
    company_id      TEXT NOT NULL REFERENCES companies(id)
);
CREATE INDEX idx_submissions_user ON submissions(user_id);
CREATE INDEX idx_submissions_rep  ON submissions(rep_id);
CREATE INDEX idx_submissions_asset ON submissions(asset_id);

CREATE TABLE feedback (
    id            TEXT PRIMARY KEY,
    submission_id TEXT NOT NULL REFERENCES submissions(id),
    company_id    TEXT NOT NULL REFERENCES companies(id),
    score         INTEGER NOT NULL,
    text          TEXT NOT NULL DEFAULT '',
    created_at    TIMESTAMPTZ NOT NULL
);
CREATE INDEX idx_feedback_submission ON feedback(submission_id);

-- RAG chunks: one asset produces many chunks.
-- source_type distinguishes asset content vs submission transcript vs feedback text.
CREATE TABLE search_chunks (
    id          TEXT PRIMARY KEY,
    content     TEXT NOT NULL,
    source_type TEXT NOT NULL,        -- 'asset' | 'submission' | 'feedback'
    source_id   TEXT NOT NULL,        -- FK to assets.id, submissions.id, or feedback.id
    company_id  TEXT NOT NULL REFERENCES companies(id),
    asset_id    TEXT REFERENCES assets(id),
    metadata    JSONB NOT NULL DEFAULT '{}',  -- page, section, timestamps, etc.
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_chunks_company  ON search_chunks(company_id);
CREATE INDEX idx_chunks_asset    ON search_chunks(asset_id);
CREATE INDEX idx_chunks_source   ON search_chunks(source_type, source_id);
