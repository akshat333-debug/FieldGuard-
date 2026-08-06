"""Unified confidence: ordering guarantees + pipeline trace wiring."""
from fieldguard.backends import MockBackend
from fieldguard.confidence import confidence
from fieldguard.pipeline import run
from fieldguard.schemas import FieldSpec, Schema

SCHEMA = Schema("invoice", (
    FieldSpec("invoice_id", "string"),
    FieldSpec("total", "number"),
))

DOC = "invoice_id: INV-0042\ntotal: 54.20"


def test_confidence_ordering():
    # resolution bands are strictly ordered at equal support
    for s in (0.0, 0.5, 1.0):
        assert (confidence("agreement", s) > confidence("majority", s)
                > confidence("split-kept", s) > 0.0)
    # pinned endpoints; note bands overlap deliberately — a fully grounded
    # majority (0.7) outranks a fully ungrounded agreement (0.5)
    assert confidence("agreement", 0.0) == 0.5
    assert confidence("agreement", 1.0) == 1.0
    assert confidence("majority", 1.0) == 0.7
    assert confidence("split-kept", 1.0) == 0.3
    assert confidence("majority", 1.0) > confidence("agreement", 0.0)


def test_pipeline_trace_carries_per_field_signals():
    trace: list[dict] = []
    (record,), report = run(MockBackend(), [DOC], SCHEMA, trace=trace)
    t = trace[0]
    assert set(t["resolution"]) == {"invoice_id", "total"}
    assert all(v == "agreement" for v in t["resolution"].values())
    assert all(0.0 <= s <= 1.0 for s in t["support"].values())
    assert all(0.0 < c <= 1.0 for c in t["confidence"].values())
    # clean agreement grounded in the doc = top confidence
    assert t["confidence"]["total"] == 1.0


def test_ground_repair_keeps_low_confidence():
    opt = Schema("s", (FieldSpec("term", "string", required=False),))
    # both paths agree on a value the document never states -> fabrication
    class Fabricator(MockBackend):
        def generate(self, prompt, *, force_json=False):
            self.calls += 1
            if force_json:
                return '{"term": "seventeen decades"}'
            return "term: seventeen decades"
    trace: list[dict] = []
    (record,), report = run(Fabricator(), ["This contract has no term clause."],
                            opt, trace=trace, ground_repair=True)
    assert record["term"] == ""            # repaired to absence
    assert report.ungrounded == 1
    # the repair must NOT launder the field into high confidence
    assert trace[0]["confidence"]["term"] < 0.7
