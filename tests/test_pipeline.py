"""End-to-end: corruption injected -> detected -> repaired -> cheaper than full verify."""
from fieldguard.data import (INVOICE_SCHEMA, PlannedMockBackend, corruption_plan,
                             make_dataset)
from fieldguard.pipeline import run


def _setup(n=20, rate=0.15):
    examples = make_dataset(n=n)
    plans = corruption_plan(examples, rate=rate)
    backend = PlannedMockBackend(examples, plans)
    docs = [ex.document for ex in examples]
    gold = [ex.gold for ex in examples]
    return backend, docs, gold, plans


def test_end_to_end_repair_and_cost():
    backend, docs, gold, plans = _setup()
    assert any(plans), "corruption plan should damage at least one field"

    finals, report = run(backend, docs, INVOICE_SCHEMA, gold=gold)

    # constraint did measurable damage; pipeline repaired all of it
    assert report.constrained_acc < 1.0
    assert report.final_acc == 1.0
    assert report.corruption_rate > 0.0
    # detector caught exactly the corrupted fields (perfect mock world)
    assert report.flag_precision == 1.0
    assert report.flag_recall == 1.0
    # selective verification beat verify-everything on cost
    assert report.llm_calls < report.full_verify_calls


def test_clean_run_no_overhead():
    examples = make_dataset(n=5)
    backend = PlannedMockBackend(examples, [{} for _ in examples])
    docs = [ex.document for ex in examples]
    gold = [ex.gold for ex in examples]

    finals, report = run(backend, docs, INVOICE_SCHEMA, gold=gold)

    assert report.constrained_acc == report.final_acc == 1.0
    assert report.corruption_rate == 0.0
    # only the two extraction calls per doc — zero arbiter overhead
    assert report.llm_calls == 2 * len(docs)


def test_report_summary_renders():
    backend, docs, gold, _ = _setup(n=5)
    _, report = run(backend, docs, INVOICE_SCHEMA, gold=gold)
    text = report.summary()
    assert "final accuracy" in text and "saved" in text


def test_micro_flag_metrics_pool_across_docs():
    """Micro P/R pool fields corpus-wide; macro averages per doc (can differ)."""
    from fieldguard.metrics import Report

    backend, docs, gold, _ = _setup(n=20, rate=0.2)
    _, report = run(backend, docs, INVOICE_SCHEMA, gold=gold)
    assert report.flag_corrupted > 0
    assert report.flag_tp == report.flag_corrupted          # perfect mock recall
    assert report.flag_precision_micro == 1.0
    assert report.flag_recall_micro == 1.0

    # empty corpus -> vacuous 1.0, no ZeroDivisionError
    blank = Report()
    assert blank.flag_precision_micro == 1.0
    assert blank.flag_recall_micro == 1.0


def test_trace_collects_duals_and_flags():
    from fieldguard.backends import MockBackend
    from fieldguard.data import make_dataset
    from fieldguard.data import INVOICE_SCHEMA
    from fieldguard.pipeline import run
    ex = make_dataset(n=2)
    trace = []
    run(MockBackend(), [e.document for e in ex], INVOICE_SCHEMA,
        gold=[e.gold for e in ex], trace=trace)
    assert len(trace) == 2
    assert set(trace[0]) == {"constrained", "unconstrained", "flagged"}
