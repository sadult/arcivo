-- Local-only organisation layer (source of truth = this database).

CREATE TABLE tags (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE COLLATE NOCASE,
    color       TEXT NOT NULL DEFAULT '#7C83FD',
    description TEXT NOT NULL DEFAULT '',
    created_at  INTEGER NOT NULL DEFAULT (strftime('%s','now'))
);

CREATE TABLE message_tags (
    account_id INTEGER NOT NULL,
    message_id INTEGER NOT NULL,
    tag_id     INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
    PRIMARY KEY (account_id, message_id, tag_id)
);
CREATE INDEX ix_message_tags_tag ON message_tags(tag_id);

-- Flags/notes survive re-syncs because they are not part of the messages row.
CREATE TABLE message_marks (
    account_id INTEGER NOT NULL,
    message_id INTEGER NOT NULL,
    flagged    INTEGER NOT NULL DEFAULT 0,
    starred    INTEGER NOT NULL DEFAULT 0,
    note       TEXT,
    updated_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
    PRIMARY KEY (account_id, message_id)
);

CREATE TABLE collections (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    query       TEXT NOT NULL,
    icon        TEXT NOT NULL DEFAULT 'sparkles',
    color       TEXT NOT NULL DEFAULT '#7C83FD',
    pinned      INTEGER NOT NULL DEFAULT 1,
    sort_key    TEXT NOT NULL DEFAULT 'date',
    sort_desc   INTEGER NOT NULL DEFAULT 1,
    description TEXT NOT NULL DEFAULT '',
    position    INTEGER NOT NULL DEFAULT 0,
    created_at  INTEGER NOT NULL DEFAULT (strftime('%s','now')),
    updated_at  INTEGER NOT NULL DEFAULT (strftime('%s','now'))
);

INSERT INTO tags(name, color) VALUES ('Important', '#F2545B'), ('Work', '#4C8DFF'), ('Music', '#B07CFF'), ('Archive', '#8A94A6');
