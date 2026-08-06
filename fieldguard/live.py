"""Instrumented single-document run: yields one event per pipeline stage.

``pipeline.run`` is the batch/evaluation entry point — it processes a corpus and
returns a Report. This module is the *interactive* entry point: same primitives,
same order, but it yields the intermediate state of every stage as it happens so
a UI can show the mechanism working rather than only its output.

Every event carries the stage's real data plus the two things a demo has to make
legible: what the stage is for, and what the output would have been without it
(``baseline`` = the constrained-only record, i.e. plain JSON mode).

Equivalence with the batch path is pinned by a test (tests/test_live.py): the
final record from ``analyze`` must equal ``pipeline.run``'s for the same
document, backend and threshold.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Iterator

from .backends import Backend
from .compare import flag_fields, normalize, normalize_set
from .confidence import confidence
from .extract import extract_constrained, extract_unconstrained
from .ground import support
from .schemas import FieldSpec, Schema
from .verify import final_record, resolve


@dataclass
class RecordingBackend:
    """Wraps a backend and keeps every (prompt, output, seconds) triple.

    The prompts ARE the mechanism — the only difference between the two
    extraction paths is the text sent to the same model at the same
    temperature — so a demo that hides them hides the claim.
    """

    inner: Backend
    log: list[dict] = field(default_factory=list)

    @property
    def calls(self) -> int:
        return self.inner.calls

    def generate(self, prompt: str, *, force_json: bool = False) -> str:
        t0 = time.perf_counter()
        out = self.inner.generate(prompt, force_json=force_json)
        self.log.append({"prompt": prompt, "output": out, "force_json": force_json,
                         "sec": round(time.perf_counter() - t0, 2)})
        return out

    def last(self) -> dict:
        return self.log[-1] if self.log else {"prompt": "", "output": "", "sec": 0.0}


def _norm_display(spec: FieldSpec, value: str) -> str:
    """Canonical form as a printable string (multi fields normalize to a set)."""
    if spec.multi:
        return "; ".join(sorted(normalize_set(spec, value)))
    return normalize(spec, value)


def analyze(backend: Backend, document: str, schema: Schema,
            threshold: float = 0.5, ground_threshold: float = 0.5,
            ground_repair: bool = False,
            gold: dict[str, str] | None = None) -> Iterator[dict]:
    """Yield stage events for one document. Blocking between yields (LLM calls)."""
    rec = RecordingBackend(backend)
    start_calls = backend.calls
    n_fields = len(schema.fields)

    yield {"stage": "source",
           "document": document,
           "fields": [{"name": f.name, "type": f.type, "required": f.required,
                       "multi": f.multi, "description": f.description,
                       "enum": list(f.enum) if f.enum else None}
                      for f in schema.fields],
           "schema": schema.name,
           "gold": gold or {}}

    constrained = extract_constrained(rec, document, schema)
    yield {"stage": "constrained", "values": constrained, **rec.last()}

    unconstrained = extract_unconstrained(rec, document, schema)
    yield {"stage": "unconstrained", "values": unconstrained, **rec.last()}

    yield {"stage": "normalize",
           "rows": [{"field": f.name,
                     "constrained": constrained[f.name],
                     "unconstrained": unconstrained[f.name],
                     "norm_constrained": _norm_display(f, constrained[f.name]),
                     "norm_unconstrained": _norm_display(f, unconstrained[f.name])}
                    for f in schema.fields]}

    flags = flag_fields(schema, constrained, unconstrained, threshold)
    flagged = {f.field: f for f in flags}
    yield {"stage": "disagree",
           "threshold": threshold,
           "flags": [{"field": f.field, "constrained": f.constrained,
                      "unconstrained": f.unconstrained, "score": round(f.score, 3)}
                     for f in flags],
           "clean": [f.name for f in schema.fields if f.name not in flagged],
           "verified": len(flags),
           "verify_everything": n_fields}

    # resolve() re-verifies every flagged field in one call; to stream progress
    # per field the loop is unrolled here over single-field resolve() calls —
    # identical work, identical order, one arbiter query each.
    resolutions = {}
    for spec in schema.fields:
        one = [flagged[spec.name]] if spec.name in flagged else []
        res = resolve(rec, document, schema, constrained, one)[spec.name]
        resolutions[spec.name] = res
        if not one:
            continue
        yield {"stage": "arbiter_field", "field": spec.name,
               "arbiter_raw": rec.last()["output"], "sec": rec.last()["sec"],
               "value": res.value, "source": res.source,
               "confident": res.confident,
               "constrained": flagged[spec.name].constrained,
               "unconstrained": flagged[spec.name].unconstrained}

    record = final_record(resolutions)
    yield {"stage": "arbiter_done",
           "resolutions": {n: {"value": r.value, "source": r.source,
                               "confident": r.confident}
                           for n, r in resolutions.items()}}

    ground_rows, supports, ungrounded_n = [], {}, 0
    for spec in schema.fields:
        s = supports[spec.name] = support(spec, record[spec.name], document)
        ok = s >= ground_threshold
        repaired = False
        if not ok:
            ungrounded_n += 1
            if ground_repair and not spec.required:
                record[spec.name] = ""
                repaired = True
        ground_rows.append({"field": spec.name, "value": record[spec.name],
                            "support": round(s, 3), "grounded": ok,
                            "repaired": repaired})
    yield {"stage": "ground", "rows": ground_rows,
           "ungrounded": ungrounded_n,
           "ungrounded_rate": round(ungrounded_n / n_fields, 3) if n_fields else 0.0,
           "threshold": ground_threshold, "repair_enabled": ground_repair}

    calls = backend.calls - start_calls
    baseline_calls = 2 + n_fields  # dual extract + one arbiter for every field
    changed = [f.name for f in schema.fields
               if _norm_display(f, record[f.name])
               != _norm_display(f, constrained[f.name])]

    final = {"stage": "kept",
             "record": record,
             "baseline": constrained,          # what plain JSON mode would ship
             # pre-repair support on purpose: a repaired field stays low
             "confidence": {n: round(confidence(r.source, supports[n]), 3)
                            for n, r in resolutions.items()},
             "changed": changed,
             "low_confidence": [n for n, r in resolutions.items() if not r.confident],
             "calls": calls,
             "verify_everything_calls": baseline_calls,
             "saved_pct": round(100 * (1 - calls / baseline_calls))
             if baseline_calls else 0}

    if gold:
        def hit(values: dict[str, str]) -> list[str]:
            return [f.name for f in schema.fields
                    if _norm_display(f, values.get(f.name, ""))
                    == _norm_display(f, gold.get(f.name, ""))]
        base_ok, final_ok = hit(constrained), hit(record)
        final["gold_eval"] = {
            "gold": gold,
            "baseline_correct": base_ok,
            "final_correct": final_ok,
            "baseline_acc": round(len(base_ok) / n_fields, 3),
            "final_acc": round(len(final_ok) / n_fields, 3),
            "repaired": sorted(set(final_ok) - set(base_ok)),
            "broken": sorted(set(base_ok) - set(final_ok)),
        }
    yield final
