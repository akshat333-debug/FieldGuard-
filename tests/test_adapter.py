"""JSONL adapter: load, schema inference, error on empty."""
import json

import pytest

from fieldguard.adapter import load_jsonl


def test_load_and_infer_schema(tmp_path):
    rows = [
        {"document": "Receipt from Joe's Diner, total $23.50, on 2026-05-01",
         "gold": {"vendor": "Joe's Diner", "total": "23.50", "date": "2026-05-01"}},
        {"document": "Receipt from Mart, total $9.99, on 2026-06-02",
         "gold": {"vendor": "Mart", "total": "9.99", "date": "2026-06-02"}},
    ]
    p = tmp_path / "data.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows))

    examples, schema = load_jsonl(p)
    assert len(examples) == 2
    assert schema.field("total").type == "number"
    assert schema.field("date").type == "date"
    assert schema.field("vendor").type == "string"


def test_empty_file_raises(tmp_path):
    p = tmp_path / "empty.jsonl"
    p.write_text("")
    with pytest.raises(ValueError):
        load_jsonl(p)
