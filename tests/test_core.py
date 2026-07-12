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
    # graded: every mismatch >= 0.5, severity scales with relative error
    near = field_disagreement(num, "54.21", "54.2")
    far = field_disagreement(num, "45", "54.2")
    huge = field_disagreement(num, "5", "-5000")  # rel error > 1 -> capped
    assert 0.5 < near < far < huge == 1.0
    s = FieldSpec("s", "string")
    assert field_disagreement(s, "Acme Corp", "acme corp") == 0.0
    assert 0.0 < field_disagreement(s, "Acme Corp", "Acme Corporation") < 1.0


def test_disagreement_dates_graded():
    d = FieldSpec("d", "date")
    off_day = field_disagreement(d, "2026-03-14", "2026-03-15")
    off_month = field_disagreement(d, "2026-03-14", "2026-04-14")
    off_years = field_disagreement(d, "2026-03-14", "2020-03-14")
    assert 0.5 < off_day < off_month < off_years == 1.0
    # unparseable garbage still max-disagrees
    assert field_disagreement(d, "2026-03-14", "not a date") == 1.0


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


def test_string_normalize_punctuation_insensitive():
    spec = FieldSpec("address", "string")
    assert (normalize(spec, "NO.53, JALAN SAGU 18, JOHOR.")
            == normalize(spec, "NO.53 JALAN SAGU 18 JOHOR"))
    # letter-level differences still distinct (real OCR misses stay visible)
    assert (normalize(spec, "MR D.T.Y. (JOHOR) SDN BHD")
            != normalize(spec, "MR D.I.Y. (JOHOR) SDN BHD"))


def test_date_normalize_strips_time_suffix():
    d = FieldSpec("d", "date")
    assert normalize(d, "05 MAR 2018 18:24") == "2018-03-05"
    assert normalize(d, "2018-03-05 18:24:59") == "2018-03-05"
    assert normalize(d, "14 March 2026, 9:05 AM") == "2026-03-14"
    # plain dates unaffected
    assert normalize(d, "05 Mar 2018") == "2018-03-05"


def test_constrained_unparseable_json_degrades_to_empty():
    class Broken(MockBackend):
        def generate(self, prompt, *, force_json=False):
            if force_json:
                return '{"invoice_id": "INV-0042", "vendor": '  # truncated JSON
            return super().generate(prompt, force_json=force_json)

    values = extract_constrained(Broken(), DOC, SCHEMA)
    assert all(v == "" for v in values.values())  # empty -> auto-flag downstream


def test_normalize_number_words_and_legalese_dates():
    s = FieldSpec("term", "string")
    assert normalize(s, "two years") == normalize(s, "2 years")
    assert normalize(s, "Five Years") == normalize(s, "5 years")
    d = FieldSpec("d", "date")
    assert normalize(d, "30th day of April, 2009") == "2009-04-30"
    assert normalize(d, "April 30, 2009") == "2009-04-30"
    assert normalize(d, "1st day of July 2026") == "2026-07-01"


def test_optional_fields_absence_semantics():
    opt = FieldSpec("term", "string", required=False)
    req = FieldSpec("total", "number")
    sch = Schema("s", (opt, req))
    # absence phrases normalize to empty for optional fields only
    assert normalize(opt, "not provided") == ""
    assert normalize(opt, "NONE") == ""
    assert normalize(req, "none") == "none"
    # both-paths-absent on an optional field = agreement, no flag
    assert flag_fields(sch, {"term": "NONE", "total": "5"},
                       {"term": "", "total": "5"}) == []
    # one-sided absence still flags
    flags = flag_fields(sch, {"term": "2 years", "total": "5"},
                        {"term": "NONE", "total": "5"})
    assert {f.field for f in flags} == {"term"}
    # required field: both-empty still auto-flags (broken-extractor guard)
    flags = flag_fields(sch, {"term": "2 years", "total": ""},
                        {"term": "2 years", "total": ""})
    assert {f.field for f in flags} == {"total"}
    # extraction prompts carry NO absence marker (it induced lazy false
    # NONEs — BUILDLOG 21); absence is structural: JSON required list only
    from fieldguard.extract import _field_lines
    assert "NONE" not in _field_lines(sch)
    assert sch.to_json_schema()["required"] == ["total"]
