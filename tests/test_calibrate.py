"""Calibration sweep: monotone cost in threshold, table renders."""
from fieldguard.calibrate import render_table, sweep
from fieldguard.data import (INVOICE_SCHEMA, PlannedMockBackend, corruption_plan,
                             make_dataset)


def test_sweep_cost_monotone_and_accuracy_tradeoff():
    examples = make_dataset(n=15)
    plans = corruption_plan(examples, rate=0.2)
    docs = [ex.document for ex in examples]
    gold = [ex.gold for ex in examples]

    points = sweep(lambda: PlannedMockBackend(examples, plans),
                   docs, INVOICE_SCHEMA, gold, thresholds=(0.1, 0.5, 0.9))

    # lower threshold can only flag more -> calls monotone non-increasing in threshold
    calls = [p.llm_calls for p in points]
    assert calls == sorted(calls, reverse=True)
    # in the mock world corruption always produces full disagreement (score 1.0
    # for typed fields), so accuracy stays perfect until threshold excludes 1.0
    assert points[0].final_acc == 1.0
    table = render_table(points)
    assert "thr" in table and len(table.splitlines()) == 5
