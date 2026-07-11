"""End-to-end orchestration: dual extract -> flag -> selective verify -> report."""
from __future__ import annotations

from .backends import Backend
from .compare import flag_fields
from .extract import dual_extract
from .metrics import Report, corrupted_fields, field_accuracy, score_flags
from .schemas import Schema
from .verify import final_record, resolve


def run(backend: Backend, documents: list[str], schema: Schema,
        gold: list[dict[str, str]] | None = None,
        threshold: float = 0.5) -> tuple[list[dict[str, str]], Report]:
    """Process documents; when gold labels are given, fill the evaluation report."""
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
        finals.append(record)

        if gold is not None:
            g = gold[i]
            con_acc_sum += field_accuracy(schema, dual.constrained, g)
            fin_acc_sum += field_accuracy(schema, record, g)
            corrupted = corrupted_fields(schema, dual.constrained,
                                         dual.unconstrained, g)
            corrupted_total += len(corrupted)
            p, r = score_flags(corrupted, {f.field for f in flags})
            prec_sum += p
            rec_sum += r

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
