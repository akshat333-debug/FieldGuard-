"""Threshold calibration: sweep the disagreement threshold, chart accuracy vs cost.

The threshold is FieldGuard's single knob: low -> more flags -> more arbiter calls
(cost) but higher recall on corrupted fields; high -> cheaper but misses corruption.
"""
from __future__ import annotations

from dataclasses import dataclass

from .backends import Backend
from .pipeline import run
from .schemas import Schema


@dataclass(frozen=True)
class CalibrationPoint:
    threshold: float
    final_acc: float
    flag_precision: float
    flag_recall: float
    llm_calls: int


def sweep(backend_factory, documents: list[str], schema: Schema,
          gold: list[dict[str, str]],
          thresholds: tuple[float, ...] = (0.1, 0.3, 0.5, 0.7, 0.9),
          ) -> list[CalibrationPoint]:
    """Run the pipeline once per threshold.

    ``backend_factory()`` must return a FRESH backend per run so call counts and
    any per-run state don't leak between sweep points.
    """
    points = []
    for t in thresholds:
        backend: Backend = backend_factory()
        _, report = run(backend, documents, schema, gold=gold, threshold=t)
        points.append(CalibrationPoint(
            threshold=t,
            final_acc=report.final_acc,
            flag_precision=report.flag_precision,
            flag_recall=report.flag_recall,
            llm_calls=report.llm_calls,
        ))
    return points


def render_table(points: list[CalibrationPoint]) -> str:
    header = f"{'thr':>4} | {'final_acc':>9} | {'flag_P':>6} | {'flag_R':>6} | {'calls':>5}"
    rows = [header, "-" * len(header)]
    rows += [f"{p.threshold:>4.2f} | {p.final_acc:>9.3f} | {p.flag_precision:>6.3f} "
             f"| {p.flag_recall:>6.3f} | {p.llm_calls:>5}" for p in points]
    return "\n".join(rows)
