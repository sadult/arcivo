-- Arcivo schema v1: accounts, messages index, peers, links, sync state, full-text search.
-- Source of truth: Telegram (messages/media). This DB is a local index + cache of that data.

CREATE TABLE accounts (
    id               INTEGER PRIMARY KEY,
    telegram_user_id INTEGER NOT NULL UNIQUE,
    display_name     TEXT,
    username         TEXT,
    created_at       INTEGER NOT NULL DEFAULT (strftime('%s','now'))
);

CREATE TABLE messages (
    rowid           INTEGER PRIMARY KEY,           -- stable rowid for FTS external content
    account_id      INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    id              INTEGER NOT NULL,              -- Telegram message id inside Saved Messages
    date_ts         INTEGER NOT NULL,              -- UTC unix seconds
    edit_ts         INTEGER,
    media_type      TEXT NOT NULL,
    category        TEXT NOT NULL,
    text            TEXT NOT NULL DEFAULT '',
    file_name       TEXT,
    extension       TEXT,
    mime_type       TEXT,
    file_size       INTEGER,
    duration        REAL,
    width           INTEGER,
    height          INTEGER,
    performer       TEXT,
    audio_title     TEXT,
    media_id        INTEGER,
    dc_id           INTEGER,
    sender_id       INTEGER,
    sender_name     TEXT,
    sender_username TEXT,
    chat_id         INTEGER,
    chat_name       TEXT,
    chat_type       TEXT,
    is_forward      INTEGER NOT NULL DEFAULT 0,
    fwd_date_ts     INTEGER,
    fwd_msg_id      INTEGER,
    reply_to_id     INTEGER,
    grouped_id      INTEGER,
    saved_peer_id   INTEGER,
    link_count      INTEGER NOT NULL DEFAULT 0,
    views           INTEGER,
    has_thumb       INTEGER NOT NULL DEFAULT 0,
    extra_json      TEXT,
    remote_deleted  INTEGER NOT NULL DEFAULT 0,   -- seen deleted on Telegram during reconcile
    synced_at       INTEGER NOT NULL,
    UNIQUE (account_id, id)
);

CREATE INDEX ix_messages_date      ON messages(account_id, date_ts);
CREATE INDEX ix_messages_type_date ON messages(account_id, media_type, date_ts);
CREATE INDEX ix_messages_category  ON messages(account_id, category, file_size);
CREATE INDEX ix_messages_size      ON messages(account_id, file_size);
CREATE INDEX ix_messages_sender    ON messages(account_id, sender_id);
CREATE INDEX ix_messages_chat      ON messages(account_id, chat_id);
CREATE INDEX ix_messages_ext       ON messages(account_id, extension);
CREATE INDEX ix_messages_media_id  ON messages(account_id, media_id);
CREATE INDEX ix_messages_grouped   ON messages(account_id, grouped_id) WHERE grouped_id IS NOT NULL;

CREATE TABLE peers (
    account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    peer_id    INTEGER NOT NULL,
    peer_type  TEXT NOT NULL,          -- user | group | channel | hidden
    name       TEXT,
    username   TEXT,
    PRIMARY KEY (account_id, peer_id, peer_type)
);

CREATE TABLE links (
    account_id INTEGER NOT NULL,
    message_id INTEGER NOT NULL,
    url        TEXT NOT NULL,
    domain     TEXT,
    PRIMARY KEY (account_id, message_id, url),
    FOREIGN KEY (account_id, message_id) REFERENCES messages(account_id, id) ON DELETE CASCADE
);
CREATE INDEX ix_links_domain ON links(account_id, domain);

CREATE TABLE sync_state (
    account_id          INTEGER PRIMARY KEY REFERENCES accounts(id) ON DELETE CASCADE,
    initial_complete    INTEGER NOT NULL DEFAULT 0,
    checkpoint_id       INTEGER NOT NULL DEFAULT 0,   -- highest contiguous id synced during initial sync
    max_message_id      INTEGER NOT NULL DEFAULT 0,
    last_full_sync      INTEGER,
    last_incremental    INTEGER,
    last_reconcile      INTEGER,
    total_synced        INTEGER NOT NULL DEFAULT 0
);

CREATE VIRTUAL TABLE messages_fts USING fts5(
    text, file_name, sender_name, chat_name, audio,
    content='',
    tokenize = "unicode61 remove_diacritics 2 tokenchars '_@.'"
);

-- contentless FTS: we keep it in sync with triggers (delete uses the special 'delete' command)
CREATE TRIGGER trg_messages_ai AFTER INSERT ON messages BEGIN
    INSERT INTO messages_fts(rowid, text, file_name, sender_name, chat_name, audio)
    VALUES (new.rowid, new.text, coalesce(new.file_name,''), coalesce(new.sender_name,'') || ' ' || coalesce(new.sender_username,''),
            coalesce(new.chat_name,''), coalesce(new.performer,'') || ' ' || coalesce(new.audio_title,''));
END;
CREATE TRIGGER trg_messages_ad AFTER DELETE ON messages BEGIN
    INSERT INTO messages_fts(messages_fts, rowid, text, file_name, sender_name, chat_name, audio)
    VALUES ('delete', old.rowid, old.text, coalesce(old.file_name,''), coalesce(old.sender_name,'') || ' ' || coalesce(old.sender_username,''),
            coalesce(old.chat_name,''), coalesce(old.performer,'') || ' ' || coalesce(old.audio_title,''));
END;
CREATE TRIGGER trg_messages_au AFTER UPDATE OF text, file_name, sender_name, sender_username, chat_name, performer, audio_title ON messages BEGIN
    INSERT INTO messages_fts(messages_fts, rowid, text, file_name, sender_name, chat_name, audio)
    VALUES ('delete', old.rowid, old.text, coalesce(old.file_name,''), coalesce(old.sender_name,'') || ' ' || coalesce(old.sender_username,''),
            coalesce(old.chat_name,''), coalesce(old.performer,'') || ' ' || coalesce(old.audio_title,''));
    INSERT INTO messages_fts(rowid, text, file_name, sender_name, chat_name, audio)
    VALUES (new.rowid, new.text, coalesce(new.file_name,''), coalesce(new.sender_name,'') || ' ' || coalesce(new.sender_username,''),
            coalesce(new.chat_name,''), coalesce(new.performer,'') || ' ' || coalesce(new.audio_title,''));
END;
