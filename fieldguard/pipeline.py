"""End-to-end orchestration: dual extract -> flag -> selective verify -> report."""
from __future__ import annotations

from .backends import Backend
from .compare import flag_fields
from .confidence import confidence
from .extract import dual_extract
from .ground import support
from .metrics import Report, corrupted_fields, field_accuracy, score_flags
from .schemas import Schema
from .verify import final_record, resolve


def run(backend: Backend, documents: list[str], schema: Schema,
        gold: list[dict[str, str]] | None = None,
        threshold: float = 0.5,
        trace: list[dict] | None = None,
        ground_repair: bool = False,
        ground_threshold: float = 0.5) -> tuple[list[dict[str, str]], Report]:
    """Process documents; when gold labels are given, fill the evaluation report.

    Pass ``trace=[]`` to collect per-doc dual outputs + flags for error analysis.

    ``ground_repair`` enables the second signal (see ``ground.py``): a value the
    source does not support, on a field that may legitimately be absent, is
    treated as a fabrication and replaced with absence. This is OFF by default
    because it is capability-dependent — measured +8.4 points on a fabricating
    model (qwen2.5:1.5b, Kleister) but -0.9 on a capable one, where the few
    ungrounded values are normalization edge cases rather than inventions.
    ``Report.ungrounded_rate`` is always computed (free, gold-independent) and
    is the runtime signal for whether to enable it: ~4% capable vs ~15%
    fabricating on the cells measured so far.
    """
    n_fields = len(schema.fields)
    report = Report(docs=len(documents), fields_total=len(documents) * n_fields)
    finals: list[dict[str, str]] = []

    con_acc_sum = fin_acc_sum = 0.0
    prec_sum = rec_sum = 0.0
    corrupted_total = 0

    for i, doc in enumerate(documents):
        dual = dual_extract(backend, doc, schema)
        flags = flag_fields(schema, dual.constrained, dual.unconstrained, threshold)
        resolutions = resolve(backend, doc, schema, dual.constrained, flags)
        record = final_record(resolutions)

        # second signal: values the source does not support (see ground.py)
        supports = {s.name: support(s, record[s.name], doc) for s in schema.fields}
        for spec in schema.fields:
            if supports[spec.name] >= ground_threshold:
                continue
            report.ungrounded += 1
            if ground_repair and not spec.required:
                record[spec.name] = ""
                # supports[] deliberately keeps the LOW pre-repair score: the
                # system just judged this field fabricated, and the confidence
                # ranking should say so even after the value is blanked

        finals.append(record)
        report.low_confidence += sum(not r.confident for r in resolutions.values())
        if trace is not None:
            trace.append({"constrained": dual.constrained,
                          "unconstrained": dual.unconstrained,
                          "flagged": sorted(f.field for f in flags),
                          "resolution": {n: r.source for n, r in resolutions.items()},
                          "support": {n: round(s, 3) for n, s in supports.items()},
                          "confidence": {n: round(confidence(r.source,
                                                             supports[n]), 3)
                                         for n, r in resolutions.items()}})

        if gold is not None:
            g = gold[i]
            con_acc_sum += field_accuracy(schema, dual.constrained, g)
            fin_acc_sum += field_accuracy(schema, record, g)
            corrupted = corrupted_fields(schema, dual.constrained,
                                         dual.unconstrained, g)
            corrupted_total += len(corrupted)
            flagged_names = {f.field for f in flags}
            p, r = score_flags(corrupted, flagged_names)
            prec_sum += p
            rec_sum += r
            report.flag_tp += len(flagged_names & corrupted)
            report.flag_flagged += len(flagged_names)
            report.flag_corrupted += len(corrupted)

    report.llm_calls = backend.calls
    # verify-everything baseline: same dual extract + one arbiter per field
    report.full_verify_calls = len(documents) * (2 + n_fields)

    if gold is not None and documents:
        n = len(documents)
        report.constrained_acc = con_acc_sum / n
        report.final_acc = fin_acc_sum / n
        report.corruption_rate = corrupted_total / report.fields_total
        report.flag_precision = prec_sum / n
        report.flag_recall = rec_sum / n

    return finals, report
