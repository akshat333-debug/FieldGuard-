"""Tests: schemas, backends, dual extraction, disagreement detection."""
import json

import pytest

from fieldguard.backends import MockBackend
from fieldguard.compare import field_disagreement, flag_fields, normalize
from fieldguard.extract import dual_extract, extract_constrained, extract_unconstrained
from fieldguard.schemas import FieldSpec, Schema

SCHEMA = Schema("invoice", (
    FieldSpec("invoice_id", "string"),
    FieldSpec("vendor", "string"),
    FieldSpec("total", "number"),
    FieldSpec("date", "date"),
    FieldSpec("currency", "enum", enum=("USD", "EUR", "INR")),
))

DOC = """invoice_id: INV-0042
vendor: Acme Corp
total: 54.20
date: 2026-03-14
currency: USD"""


def test_schema_validation():
    with pytest.raises(ValueError):
        FieldSpec("x", "floaty")
    with pytest.raises(ValueError):
        FieldSpec("x", "enum")  # enum without values
    js = SCHEMA.to_json_schema()
    assert js["properties"]["total"]["type"] == "number"
    assert js["properties"]["currency"]["enum"] == ["USD", "EUR", "INR"]
    assert js["required"] == [f.name for f in SCHEMA.fields]


def test_normalize_numbers_dates_strings():
    num = FieldSpec("n", "number")
    assert normalize(num, "$54.20") == normalize(num, "54.2")
    assert normalize(num, "1,234") == normalize(num, "1234")
    date = FieldSpec("d", "date")
    assert normalize(date, "2026-03-14") == normalize(date, "14 March 2026")
    s = FieldSpec("s", "string")
    assert normalize(s, "  Acme   Corp ") == normalize(s, "acme corp")


def test_disagreement_scores():
    num = FieldSpec("n", "number")
    assert field_disagreement(num, "$54.20", "54.2") == 0.0
    assert field_disagreement(num, "45", "54.2") == 1.0
    s = FieldSpec("s", "string")
    assert field_disagreement(s, "Acme Corp", "acme corp") == 0.0
    assert 0.0 < field_disagreement(s, "Acme Corp", "Acme Corporation") < 1.0


def test_mock_backend_corrupts_only_constrained():
    clean = MockBackend()
    dual = dual_extract(clean, DOC, SCHEMA)
    assert dual.constrained == dual.unconstrained
    assert dual.constrained["total"] == "54.20"

    corrupt = MockBackend(corruptions={"total": "45", "date": "2026-03-04"})
    dual = dual_extract(corrupt, DOC, SCHEMA)
    assert dual.constrained["total"] == "45"          # corrupted
    assert dual.unconstrained["total"] == "54.20"     # untouched
    assert corrupt.calls == 2


def test_constrained_parses_fenced_json():
    class Fenced(MockBackend):
        def generate(self, prompt, *, force_json=False):
            out = super().generate(prompt, force_json=force_json)
            return f"```json\n{out}\n```" if force_json else out

    values = extract_constrained(Fenced(), DOC, SCHEMA)
    assert values["vendor"] == "Acme Corp"


def test_flag_fields_finds_exactly_corrupted():
    corrupt = MockBackend(corruptions={"total": "45", "vendor": "Ajax Corp"})
    dual = dual_extract(corrupt, DOC, SCHEMA)
    flags = flag_fields(SCHEMA, dual.constrained, dual.unconstrained)
    assert {f.field for f in flags} == {"total", "vendor"}


def test_no_flags_when_clean():
    dual = dual_extract(MockBackend(), DOC, SCHEMA)
    assert flag_fields(SCHEMA, dual.constrained, dual.unconstrained) == []
