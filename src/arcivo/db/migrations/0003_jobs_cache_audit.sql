-- Jobs, reports, cache registry and an append-only audit log for destructive operations.

CREATE TABLE jobs (
    id          TEXT PRIMARY KEY,
    kind        TEXT NOT NULL,              -- export | delete | sync | download
    title       TEXT NOT NULL,
    status      TEXT NOT NULL,
    params_json TEXT NOT NULL,
    progress_json TEXT NOT NULL DEFAULT '{}',
    error       TEXT,
    created_at  INTEGER NOT NULL,
    started_at  INTEGER,
    finished_at INTEGER
);
CREATE INDEX ix_jobs_created ON jobs(created_at);

CREATE TABLE job_items (
    job_id     TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    message_id INTEGER NOT NULL,
    status     TEXT NOT NULL,              -- pending | done | failed | skipped
    bytes      INTEGER,
    path       TEXT,
    error      TEXT,
    PRIMARY KEY (job_id, message_id)
);

CREATE TABLE reports (
    id           INTEGER PRIMARY KEY,
    job_id       TEXT REFERENCES jobs(id) ON DELETE SET NULL,
    kind         TEXT NOT NULL,
    summary_json TEXT NOT NULL,
    json_path    TEXT,
    html_path    TEXT,
    created_at   INTEGER NOT NULL
);

CREATE TABLE cache_entries (
    account_id  INTEGER NOT NULL,
    message_id  INTEGER NOT NULL,
    kind        TEXT NOT NULL,             -- thumb | preview
    path        TEXT NOT NULL,
    size        INTEGER NOT NULL,
    sha256      TEXT,
    created_at  INTEGER NOT NULL,
    last_used   INTEGER NOT NULL,
    PRIMARY KEY (account_id, message_id, kind)
);
CREATE INDEX ix_cache_last_used ON cache_entries(last_used);

-- Hashes of fully downloaded/exported files (for exact duplicate detection)
CREATE TABLE file_hashes (
    account_id INTEGER NOT NULL,
    message_id INTEGER NOT NULL,
    sha256     TEXT NOT NULL,
    size       INTEGER NOT NULL,
    PRIMARY KEY (account_id, message_id)
);
CREATE INDEX ix_file_hashes_sha ON file_hashes(sha256);

CREATE TABLE audit_log (
    id       INTEGER PRIMARY KEY,
    ts       INTEGER NOT NULL,
    action   TEXT NOT NULL,
    details  TEXT NOT NULL
);
