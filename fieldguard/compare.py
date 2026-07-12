"""Core mechanism: type-aware normalization + per-field disagreement scoring."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from .schemas import FieldSpec, Schema

# ponytail: fixed format list, not a general date parser; extend list (or swap in
# dateutil) when real benchmark data shows unparsed formats.
_DATE_FORMATS = ("%Y-%m-%d", "%d %B %Y", "%B %d, %Y", "%d/%m/%Y", "%m/%d/%Y",
                 "%d-%m-%Y", "%b %d, %Y", "%d %b %Y")

_NUM_JUNK = re.compile(r"[$€£₹,\s]|(?:USD|EUR|GBP|INR|MYR|RM)", re.I)


def normalize(spec: FieldSpec, value: str) -> str:
    """Canonical string form for equality comparison. Empty string if unparseable."""
    v = value.strip()
    if not v:
        return ""
    if spec.type in ("number", "integer"):
        cleaned = _NUM_JUNK.sub("", v)
        try:
            f = float(cleaned)
        except ValueError:
            return v.casefold()
        return str(int(f)) if f == int(f) else repr(f)
    if spec.type == "date":
        # free-form answers often append time-of-day ("14 MAR 2018 18:40")
        v_date = re.sub(r"[,\s]*\d{1,2}:\d{2}(:\d{2})?\s*(AM|PM)?\s*$", "", v,
                        flags=re.I).strip()
        for fmt in _DATE_FORMATS:
            try:
                return datetime.strptime(v_date, fmt).date().isoformat()
            except ValueError:
                continue
        return v.casefold()
    # string / enum — punctuation-insensitive: real OCR benchmarks (SROIE) differ
    # from gold in trailing periods/commas/spacing, which is not an extraction error
    v = re.sub(r"[^\w\s&/@-]", " ", v)
    return re.sub(r"\s+", " ", v).strip().casefold()


def _token_jaccard_distance(a: str, b: str) -> float:
    ta, tb = set(a.split()), set(b.split())
    if not ta and not tb:
        return 0.0
    return 1.0 - len(ta & tb) / len(ta | tb)


def field_disagreement(spec: FieldSpec, a: str, b: str) -> float:
    """0.0 = agree, 1.0 = max disagree; mismatches grade by severity.

    Typed mismatches map to 0.5 + 0.5*severity so every mismatch clears the 0.5
    default threshold (back-compat) while thresholds in (0.5, 1.0] become a real
    knob: skip near-agreements (rounding, off-by-a-day), keep gross corruption.
    """
    na, nb = normalize(spec, a), normalize(spec, b)
    if na == nb:
        return 0.0
    if spec.type == "string":
        return _token_jaccard_distance(na, nb)
    if spec.type in ("number", "integer"):
        try:
            fa, fb = float(na), float(nb)
        except ValueError:
            return 1.0
        rel = abs(fa - fb) / max(abs(fa), abs(fb))  # na != nb, so not both 0
        return 0.5 + 0.5 * min(1.0, rel)
    if spec.type == "date":
        try:
            da, db = datetime.fromisoformat(na), datetime.fromisoformat(nb)
        except ValueError:
            return 1.0
        days = abs((da - db).days)
        return 0.5 + 0.5 * min(1.0, days / 365.0)
    return 1.0


@dataclass(frozen=True)
class Flag:
    field: str
    constrained: str
    unconstrained: str
    score: float


def flag_fields(schema: Schema, constrained: dict[str, str],
                unconstrained: dict[str, str], threshold: float = 0.5) -> list[Flag]:
    """Fields where the two generation paths disagree — likely constraint-corrupted."""
    flags = []
    for f in schema.fields:
        a, b = constrained.get(f.name, ""), unconstrained.get(f.name, "")
        # empty required field is always suspicious — catches the correlated
        # both-paths-empty failure that plain disagreement can't see
        if not a.strip() or not b.strip():
            flags.append(Flag(f.name, a, b, 1.0))
            continue
        score = field_disagreement(f, a, b)
        if score >= threshold:
            flags.append(Flag(f.name, a, b, score))
    return flags
