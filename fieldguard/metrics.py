"""Evaluation: field accuracy, corruption rate, flag precision/recall, cost."""
from __future__ import annotations

from dataclasses import dataclass, field

from .compare import normalize, normalize_set
from .schemas import Schema


def _eq(schema: Schema, name: str, a: str, b: str) -> bool:
    spec = schema.field(name)
    if spec.multi:
        return normalize_set(spec, a) == normalize_set(spec, b)
    return normalize(spec, a) == normalize(spec, b)


def field_accuracy(schema: Schema, predicted: dict[str, str],
                   gold: dict[str, str]) -> float:
    names = [f.name for f in schema.fields]
    correct = sum(_eq(schema, n, predicted.get(n, ""), gold[n]) for n in names)
    return correct / len(names)


def corrupted_fields(schema: Schema, constrained: dict[str, str],
                     unconstrained: dict[str, str], gold: dict[str, str]) -> set[str]:
    """Fields where the constraint did damage: constrained wrong AND unconstrained right."""
    return {f.name for f in schema.fields
            if not _eq(schema, f.name, constrained.get(f.name, ""), gold[f.name])
            and _eq(schema, f.name, unconstrained.get(f.name, ""), gold[f.name])}


@dataclass
class Report:
    docs: int = 0
    fields_total: int = 0
    constrained_acc: float = 0.0
    final_acc: float = 0.0
    corruption_rate: float = 0.0     # share of fields damaged by the constraint
    flag_precision: float = 0.0
    flag_recall: float = 0.0
    llm_calls: int = 0
    full_verify_calls: int = 0       # what verify-everything would have cost
    low_confidence: int = 0          # fields the system itself marked unreliable
    notes: list[str] = field(default_factory=list)

    def summary(self) -> str:
        saved = self.full_verify_calls and (
            1 - (self.llm_calls / self.full_verify_calls))
        return (
            f"docs={self.docs} fields={self.fields_total}\n"
            f"constrained accuracy : {self.constrained_acc:.3f}\n"
            f"final accuracy       : {self.final_acc:.3f}\n"
            f"corruption rate      : {self.corruption_rate:.3f}\n"
            f"flag precision/recall: {self.flag_precision:.3f} / {self.flag_recall:.3f}\n"
            f"LLM calls used       : {self.llm_calls} "
            f"(verify-everything baseline: {self.full_verify_calls}, "
            f"saved {saved:.0%})\n"
            f"low-confidence fields: {self.low_confidence}/{self.fields_total}"
        )


def score_flags(corrupted: set[str], flagged: set[str]) -> tuple[float, float]:
    """(precision, recall) of flagged set vs actually-corrupted set."""
    if not flagged:
        return (1.0 if not corrupted else 0.0, 1.0 if not corrupted else 0.0)
    tp = len(flagged & corrupted)
    precision = tp / len(flagged)
    recall = tp / len(corrupted) if corrupted else 1.0
    return precision, recall
