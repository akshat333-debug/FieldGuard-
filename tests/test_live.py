"""The live (streamed) path must produce exactly what the batch path produces."""
from __future__ import annotations

from fieldguard.backends import MockBackend
from fieldguard.live import analyze
from fieldguard.pipeline import run
from fieldguard.schemas import FieldSpec, Schema

SCHEMA = Schema("invoice", (
    FieldSpec("invoice_id", "string"),
    FieldSpec("vendor", "string"),
    FieldSpec("total", "number"),
    FieldSpec("date", "date"),
))

DOC = """invoice_id: INV-0042
vendor: Acme Corp
total: 54.20
date: 2026-03-14"""

CORRUPTIONS = {"total": "45", "vendor": "Ajax Corp"}


def _events(**kw) -> dict[str, dict]:
    backend = MockBackend(corruptions=CORRUPTIONS)
    out = {}
    for ev in analyze(backend, DOC, SCHEMA, **kw):
        out.setdefault(ev["stage"], ev)
        out[f"_calls"] = backend.calls
    return out


def test_live_matches_batch_pipeline():
    (batch_record,), report = run(MockBackend(corruptions=CORRUPTIONS),
                                  [DOC], SCHEMA)
    ev = _events()
    assert ev["kept"]["record"] == batch_record
    # same work, not just the same answer
    assert ev["_calls"] == report.llm_calls
    assert ev["kept"]["verify_everything_calls"] == report.full_verify_calls


def test_live_stage_order_and_payloads():
    stages = [e["stage"] for e in
              analyze(MockBackend(corruptions=CORRUPTIONS), DOC, SCHEMA)]
    assert stages[:5] == ["source", "constrained", "unconstrained",
                          "normalize", "disagree"]
    assert stages[-1] == "kept"
    assert stages.count("arbiter_field") == len(CORRUPTIONS)  # one per flag


def test_live_reports_counterfactual_against_gold():
    gold = {"invoice_id": "INV-0042", "vendor": "Acme Corp",
            "total": "54.20", "date": "2026-03-14"}
    kept = _events(gold=gold)["kept"]
    # the constrained-only baseline is what plain JSON mode would have shipped
    assert kept["baseline"]["total"] == "45"
    assert kept["record"]["total"] == "54.20"
    ge = kept["gold_eval"]
    assert sorted(ge["repaired"]) == ["total", "vendor"]
    assert ge["broken"] == []
    assert ge["baseline_acc"] == 0.5 and ge["final_acc"] == 1.0


def test_live_grounding_stage_scores_every_field():
    rows = _events()["ground"]["rows"]
    assert [r["field"] for r in rows] == [f.name for f in SCHEMA.fields]
    assert all(0.0 <= r["support"] <= 1.0 for r in rows)
