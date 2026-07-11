"""Regressions from the first real-model run (qwen2.5:3b)."""
from fieldguard.backends import MockBackend
from fieldguard.extract import extract_unconstrained
from fieldguard.schemas import FieldSpec, Schema
from fieldguard.verify import _clean_answer

SCHEMA = Schema("invoice", (
    FieldSpec("invoice_id", "string"),
    FieldSpec("total", "number"),
    FieldSpec("currency", "enum", enum=("USD", "EUR", "INR")),
))

DOC = "invoice_id: INV-9\ntotal: 12.50\ncurrency: EUR"


def test_unconstrained_parser_survives_markdown_and_case():
    class Messy(MockBackend):
        def generate(self, prompt, *, force_json=False):
            self.calls += 1
            return ("- **Invoice_ID**: INV-9\n"
                    "* TOTAL: 12.50\n"
                    "> currency: EUR\n"
                    "Some trailing chatter: ignore me\n")

    values = extract_unconstrained(Messy(), DOC, SCHEMA)
    assert values == {"invoice_id": "INV-9", "total": "12.50", "currency": "EUR"}


def test_clean_answer_enum_strips_cruft():
    spec = SCHEMA.field("currency")
    assert _clean_answer(spec, "USD 600.45") == "USD"
    assert _clean_answer(spec, "The currency is eur.") == "EUR"


def test_clean_answer_number_extracts_value():
    spec = SCHEMA.field("total")
    assert _clean_answer(spec, "The total is 9,478.23.") == "9,478.23"
    assert _clean_answer(spec, "54.20") == "54.20"


def test_clean_answer_string_passthrough():
    spec = SCHEMA.field("invoice_id")
    assert _clean_answer(spec, '"INV-9".') == "INV-9"


def test_empty_fields_always_flagged():
    """Correlated failure: both paths empty must still flag (tinyllama finding)."""
    from fieldguard.compare import flag_fields
    empty = {f.name: "" for f in SCHEMA.fields}
    flags = flag_fields(SCHEMA, empty, empty)
    assert {f.field for f in flags} == {f.name for f in SCHEMA.fields}
    assert all(f.score == 1.0 for f in flags)
