"""Deterministic synthetic invoice dataset with gold labels (offline development).

# ponytail: synthetic invoices only; real-benchmark adapters (ExtractBench etc.)
# plug in later — pipeline only needs (documents, gold, schema).
"""
from __future__ import annotations

import random
from dataclasses import dataclass

from .backends import MockBackend, _document_block
from .schemas import FieldSpec, Schema

INVOICE_SCHEMA = Schema("invoice", (
    FieldSpec("invoice_id", "string"),
    FieldSpec("vendor", "string"),
    FieldSpec("total", "number"),
    FieldSpec("date", "date"),
    FieldSpec("currency", "enum", enum=("USD", "EUR", "INR")),
))

_VENDORS = ("Acme Corp", "Globex Ltd", "Initech", "Umbrella Supplies",
            "Stark Industries", "Wayne Enterprises")


@dataclass(frozen=True)
class Example:
    document: str
    gold: dict[str, str]


def make_dataset(n: int = 20, seed: int = 7) -> list[Example]:
    rng = random.Random(seed)
    out = []
    for i in range(n):
        gold = {
            "invoice_id": f"INV-{1000 + i}",
            "vendor": rng.choice(_VENDORS),
            "total": f"{rng.uniform(10, 9999):.2f}",
            "date": f"2026-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}",
            "currency": rng.choice(("USD", "EUR", "INR")),
        }
        doc = "\n".join(f"{k}: {v}" for k, v in gold.items())
        out.append(Example(document=doc, gold=gold))
    return out


def corruption_plan(examples: list[Example], rate: float = 0.15,
                    seed: int = 13) -> list[dict[str, str]]:
    """Per-document corruption tables for MockBackend: ~rate of fields damaged.

    Damage styles mirror real constraint failures: digit swaps in numbers,
    day/month shifts in dates, truncated strings, wrong-but-valid enum picks.
    """
    rng = random.Random(seed)
    plans: list[dict[str, str]] = []
    for ex in examples:
        plan: dict[str, str] = {}
        for name, value in ex.gold.items():
            if rng.random() >= rate:
                continue
            if name == "total":
                digits = value.replace(".", "")
                plan[name] = value[::-1] if len(set(digits)) == 1 else \
                    value.replace(value[0], str((int(value[0]) + 3) % 10), 1)
            elif name == "date":
                y, m, d = value.split("-")
                plan[name] = f"{y}-{m}-{(int(d) % 28) + 1:02d}"
            elif name == "currency":
                plan[name] = {"USD": "EUR", "EUR": "INR", "INR": "USD"}[value]
            else:
                plan[name] = value.split()[0] if " " in value else value[:3]
        plans.append(plan)
    return plans


_MONTHS = ("January", "February", "March", "April", "May", "June", "July",
           "August", "September", "October", "November", "December")


def render_realistic(ex: Example) -> str:
    """Prose invoice rendering for real-model runs: same gold, harder surface form.

    Dates appear as '14 March 2026', totals as 'USD 1,234.50' — the model must
    extract and the comparator must normalize. Mock backends can't parse these
    (no 'field: value' lines); use only with real backends.
    """
    g = ex.gold
    y, m, d = g["date"].split("-")
    date_words = f"{int(d)} {_MONTHS[int(m) - 1]} {y}"
    total = f"{float(g['total']):,.2f}"
    return (
        f"INVOICE\n"
        f"Number: {g['invoice_id']}\n"
        f"Issued by {g['vendor']} on {date_words}.\n"
        f"Amount due: {g['currency']} {total}\n"
        f"Please remit payment within 30 days of the issue date.\n"
    )


class PlannedMockBackend(MockBackend):
    """MockBackend that applies a per-document corruption plan (keyed by invoice_id)."""

    def __init__(self, examples: list[Example], plans: list[dict[str, str]]):
        super().__init__()
        self._by_id = {ex.gold["invoice_id"]: plan
                       for ex, plan in zip(examples, plans)}

    def generate(self, prompt: str, *, force_json: bool = False) -> str:
        doc_vals = self._read_values(_document_block(prompt))
        self.corruptions = self._by_id.get(doc_vals.get("invoice_id", ""), {})
        return super().generate(prompt, force_json=force_json)
