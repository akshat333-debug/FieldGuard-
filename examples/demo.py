"""Offline FieldGuard demo: synthetic invoices, injected constraint corruption,
detection, selective repair, cost report.

Run:  python3 -m examples.demo
"""
from fieldguard.data import (INVOICE_SCHEMA, PlannedMockBackend, corruption_plan,
                             make_dataset)
from fieldguard.pipeline import run


def main() -> None:
    examples = make_dataset(n=25)
    plans = corruption_plan(examples, rate=0.15)
    backend = PlannedMockBackend(examples, plans)

    docs = [ex.document for ex in examples]
    gold = [ex.gold for ex in examples]

    n_corrupted = sum(len(p) for p in plans)
    print(f"FieldGuard demo — {len(docs)} invoices, "
          f"{n_corrupted} fields corrupted by the (simulated) constraint\n")

    finals, report = run(backend, docs, INVOICE_SCHEMA, gold=gold)

    print(report.summary())
    print("\nExample repair (doc 0 corruption plan:", plans[0] or "clean", ")")
    for name, value in finals[0].items():
        print(f"  {name:<11} = {value}")


if __name__ == "__main__":
    main()
