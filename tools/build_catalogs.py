"""Regenerate src/arcivo/i18n/locales/en.json from tools/i18n_en.py (flat → nested)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from i18n_en import EN


def nest(flat):
    out = {}
    for k, v in sorted(flat.items()):
        node = out
        parts = k.split(".")
        for p in parts[:-1]:
            node = node.setdefault(p, {})
        node[parts[-1]] = v
    return out


root = Path(__file__).resolve().parents[1] / "src/arcivo/i18n/locales"
(root / "en.json").write_text(json.dumps(nest(EN), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
print("ok", len(EN))
