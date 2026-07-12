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


def test_dmy_date_inferred_and_currency_rm_stripped(tmp_path):
    # SROIE-shaped record: dd/mm/yyyy gold date, ringgit amounts in text
    rows = [{"document": "TOTAL RM 9.00 DATE 25/12/2018",
             "gold": {"date": "25/12/2018", "total": "9.00"}}]
    p = tmp_path / "sroie.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows))
    _, schema = load_jsonl(p)
    assert schema.field("date").type == "date"
    from fieldguard.compare import normalize
    assert normalize(schema.field("total"), "RM 9.00") == "9"
    assert normalize(schema.field("date"), "25/12/2018") == "2018-12-25"


def test_sroie_box_text_keeps_commas():
    from examples.convert_sroie import box_to_text
    import pathlib, tempfile
    with tempfile.TemporaryDirectory() as d:
        p = pathlib.Path(d) / "b.csv"
        p.write_text("1,2,3,4,5,6,7,8,NO.53 55,57 & 59, JALAN SAGU 18,\n"
                     "1,2,3,4,5,6,7,8,TOTAL RM 9.00")
        assert box_to_text(p) == "NO.53 55,57 & 59, JALAN SAGU 18,\nTOTAL RM 9.00"


def test_schema_from_json_descriptions_flow_to_prompts(tmp_path):
    from fieldguard.adapter import schema_from_json
    from fieldguard.extract import _field_lines
    p = tmp_path / "s.json"
    p.write_text(json.dumps({"name": "r", "fields": [
        {"name": "company", "type": "string",
         "description": "issuing business, not a person"}]}))
    schema = schema_from_json(p)
    assert schema.field("company").description == "issuing business, not a person"
    assert "issuing business, not a person" in _field_lines(schema)
    assert "description" in json.dumps(schema.to_json_schema())
