from arcivo.db.database import Database
from arcivo.db.migrator import _split, current_version, discover, migrate


def test_migrations_apply_and_idempotent(tmp_path):
    db = Database(tmp_path / "a.db")
    applied = migrate(db, tmp_path / "bk")
    assert applied == [m.version for m in discover()]
    assert migrate(db, tmp_path / "bk") == []
    assert current_version(db) == applied[-1]
    assert db.integrity_check() == "ok"
    names = {r[0] for r in db.query("SELECT name FROM sqlite_master WHERE type IN ('table','trigger')")}
    assert {"messages", "messages_fts", "tags", "jobs", "audit_log", "trg_messages_ai"} <= names


def test_split_keeps_triggers():
    sql = "CREATE TABLE a(x);\nCREATE TRIGGER t AFTER INSERT ON a BEGIN\n  SELECT 1;\n  SELECT 2;\nEND;\nCREATE INDEX i ON a(x);"
    parts = _split(sql)
    assert len(parts) == 3 and parts[1].strip().endswith("END;")


def test_fts_triggers(ctx, records):
    aid = ctx.accounts.ensure(1, "Me")
    ctx.messages.upsert_many(aid, records[:50])
    assert ctx.search.count(aid, "") == 50
    some = next(r for r in records[:50] if r.text)
    word = some.text.split()[0]
    assert ctx.search.count(aid, word) >= 1
    # update text → FTS reflects change
    some.text = "zebracorn unique"
    ctx.messages.upsert_many(aid, [some])
    assert ctx.search.count(aid, "zebracorn") == 1
    ctx.messages.delete_local(aid, [some.id])
    assert ctx.search.count(aid, "zebracorn") == 0
