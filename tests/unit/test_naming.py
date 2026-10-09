from pathlib import Path

from arcivo.export.naming import (
    build_relative_path,
    context_for,
    sanitize_component,
    unique_path,
    validate_template,
)


def test_sanitize_windows():
    assert sanitize_component('a<b>c:d"e/f\\g|h?i*j') == "a_b_c_d_e_f_g_h_i_j"
    assert sanitize_component("CON") == "_CON"
    assert sanitize_component("nul.txt") == "_nul.txt"
    assert sanitize_component("trailing. . ") == "trailing"
    assert sanitize_component("") == "_"
    long = sanitize_component("x" * 300 + ".pdf")
    assert len(long) <= 120 and long.endswith(".pdf")


def test_templates():
    row = {"id": 5, "date_ts": 1767225600, "media_type": "document", "category": "documents", "file_name": "Report: Q1?.pdf",
           "extension": "pdf", "sender_name": "Sara/Ahmadi", "chat_name": None, "is_forward": 0, "file_size": 10}
    ctx = context_for(row)
    p = build_relative_path("{chat}/{year}/{type}", "{date}_{sender}_{filename}", ctx)
    assert p.parts[0] == "Saved Messages" and p.parts[2] == "document"
    assert p.name.endswith("Sara_Ahmadi_Report_ Q1_.pdf")
    assert validate_template("{chat}/{bogus}") == ["bogus"]


def test_unique_path(tmp_path: Path):
    f = tmp_path / "a.txt"
    f.write_text("x")
    taken: set[str] = set()
    assert unique_path(f, taken).name == "a (1).txt"
    assert unique_path(f, taken).name == "a (2).txt"
