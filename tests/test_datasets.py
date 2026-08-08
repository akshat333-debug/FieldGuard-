"""Offline guards on the shipped benchmark files.

Full provenance (re-derivation from the official releases) lives in
`examples/verify_datasets.py` and needs network. These checks need none, and
exist so a regression in a converter or an accidental edit to a dataset shows
up in the ordinary test run rather than in a benchmark number three hours later.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from fieldguard.adapter import load_jsonl, schema_from_json

DATASETS = pathlib.Path(__file__).resolve().parent.parent / "datasets"

# (file, schema, expected records, expected gold keys)
CORPORA = [
    ("kleister_nda.jsonl", "kleister_nda.schema.json", 83,
     {"effective_date", "jurisdiction", "term"}),
    ("kleister_nda_party.jsonl", "kleister_nda_party.schema.json", 83,
     {"effective_date", "jurisdiction", "term", "party"}),
    ("sroie_50.jsonl", "sroie.schema.json", 50,
     {"company", "date", "address", "total"}),
    ("sroie_15.jsonl", "sroie.schema.json", 15,
     {"company", "date", "address", "total"}),
]


@pytest.mark.parametrize("name,schema_name,n,keys", CORPORA)
def test_shipped_corpus_shape(name, schema_name, n, keys):
    """Record count and gold keys are the split we claim in docs/DATA.md."""
    records = [json.loads(l) for l in
               (DATASETS / name).read_text().splitlines() if l.strip()]
    assert len(records) == n
    assert all(set(r["gold"]) == keys for r in records)
    assert all(r["document"].strip() for r in records)


@pytest.mark.parametrize("name,schema_name,n,keys", CORPORA)
def test_corpus_loads_against_its_schema(name, schema_name, n, keys):
    schema = schema_from_json(DATASETS / schema_name)
    examples, _ = load_jsonl(DATASETS / name, schema=schema)
    assert len(examples) == n
    assert {f.name for f in schema.fields} == keys


def test_no_literal_escape_sequences_survive_conversion():
    """The upstream Kleister TSV escapes newlines; converted text must not.

    This is the bug of BUILDLOG 36 — 5816 fake '\\n' per file reaching the
    model — pinned so it cannot come back silently.
    """
    for name in ("kleister_nda.jsonl", "kleister_nda_party.jsonl"):
        text = (DATASETS / name).read_text()
        records = [json.loads(l) for l in text.splitlines() if l.strip()]
        literal = sum(r["document"].count("\\n") + r["document"].count("\\t")
                      for r in records)
        assert literal == 0, f"{name}: {literal} literal escape sequences"
        # and real newlines ARE present, i.e. we did not strip structure instead
        assert sum(r["document"].count("\n") for r in records) > 1000


def test_kleister_absence_share_matches_documented_split():
    """75 of 249 dev-0 gold fields are legitimately absent (docs/DATA.md)."""
    records = [json.loads(l) for l in
               (DATASETS / "kleister_nda.jsonl").read_text().splitlines()]
    empty = sum(1 for r in records for v in r["gold"].values() if v == "")
    assert empty == 75
    assert len(records) * 3 == 249
