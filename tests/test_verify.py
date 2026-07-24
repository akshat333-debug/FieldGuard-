"""Tests: selective re-verification resolves corrupted fields at minimal cost."""
from fieldguard.backends import MockBackend
from fieldguard.compare import flag_fields
from fieldguard.extract import dual_extract
from fieldguard.schemas import FieldSpec, Schema
from fieldguard.verify import final_record, resolve

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


def test_resolve_repairs_corrupted_fields():
    backend = MockBackend(corruptions={"total": "45", "date": "2026-03-04"})
    dual = dual_extract(backend, DOC, SCHEMA)
    flags = flag_fields(SCHEMA, dual.constrained, dual.unconstrained)
    assert {f.field for f in flags} == {"total", "date"}

    calls_before = backend.calls
    res = resolve(backend, DOC, SCHEMA, dual.constrained, flags)
    record = final_record(res)

    assert record["total"] == "54.20"        # repaired
    assert record["date"] == "2026-03-14"    # repaired
    assert record["invoice_id"] == "INV-0042"
    # arbiter agreed with unconstrained -> confident majority
    assert res["total"].source == "majority" and res["total"].confident
    # unflagged fields cost nothing
    assert res["vendor"].source == "agreement"
    # selective cost: only 2 arbiter calls, not one per field
    assert backend.calls - calls_before == 2


def test_resolve_clean_document_costs_zero():
    backend = MockBackend()
    dual = dual_extract(backend, DOC, SCHEMA)
    flags = flag_fields(SCHEMA, dual.constrained, dual.unconstrained)
    calls_before = backend.calls
    res = resolve(backend, DOC, SCHEMA, dual.constrained, flags)
    assert backend.calls == calls_before          # no arbiter calls
    assert final_record(res)["total"] == "54.20"
    assert all(r.confident for r in res.values())


def test_three_way_split_keeps_constrained_low_confidence():
    class SplitArbiter(MockBackend):
        def generate(self, prompt, *, force_json=False):
            if "FIELD: total" in prompt:
                self.calls += 1
                return "99.99"  # disagrees with both paths
            return super().generate(prompt, force_json=force_json)

    backend = SplitArbiter(corruptions={"total": "45"})
    dual = dual_extract(backend, DOC, SCHEMA)
    flags = flag_fields(SCHEMA, dual.constrained, dual.unconstrained)
    res = resolve(backend, DOC, SCHEMA, dual.constrained, flags)
    # uncorroborated flag: keep production (constrained) output, mark unreliable
    assert res["total"].source == "split-kept"
    assert res["total"].value == "45"
    assert not res["total"].confident


def test_multi_value_resolution_is_order_insensitive():
    """Resolution must use set equality for multi fields (audit bug).

    Scalar normalize is order-sensitive, so an arbiter corroborating a path in a
    different order was scored a three-way split: wrong value kept, confidence
    wrongly lowered.
    """
    from fieldguard.compare import Flag
    from fieldguard.schemas import FieldSpec, Schema

    party = FieldSpec("party", "string", multi=True)
    sch = Schema("s", (party,))

    class Arb(MockBackend):
        def generate(self, prompt, *, force_json=False):
            self.calls += 1
            return "Beta LLC; Acme Corp"      # unconstrained's set, other order

    flags = [Flag("party", "Acme Corp", "Acme Corp; Beta LLC", 1.0)]
    res = resolve(Arb(), "doc", sch, {"party": "Acme Corp"}, flags)["party"]
    assert res.source == "majority"
    assert res.confident
    assert res.value == "Beta LLC; Acme Corp"


def test_arbiter_stays_blind_to_candidates():
    # regression for BUILDLOG iteration 19: a candidate-aware arbiter parrots
    # refusal candidates and manufactures false majorities — keep it blind
    seen = {}

    class Spy(MockBackend):
        def generate(self, prompt, *, force_json=False):
            if "FIELD: total" in prompt:
                seen["prompt"] = prompt
            return super().generate(prompt, force_json=force_json)

    backend = Spy(corruptions={"total": "45"})
    dual = dual_extract(backend, DOC, SCHEMA)
    flags = flag_fields(SCHEMA, dual.constrained, dual.unconstrained)
    resolve(backend, DOC, SCHEMA, dual.constrained, flags)
    assert "45" not in seen["prompt"].split("DOCUMENT:")[0]  # no candidate leak
    assert "CANDIDATES" not in seen["prompt"]
