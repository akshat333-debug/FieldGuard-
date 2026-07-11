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

_NUM_JUNK = re.compile(r"[$€£₹,\s]|(?:USD|EUR|GBP|INR)", re.I)


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
        for fmt in _DATE_FORMATS:
            try:
                return datetime.strptime(v, fmt).date().isoformat()
            except ValueError:
                continue
        return v.casefold()
    # string / enum
    return re.sub(r"\s+", " ", v).casefold()


def _token_jaccard_distance(a: str, b: str) -> float:
    ta, tb = set(a.split()), set(b.split())
    if not ta and not tb:
        return 0.0
    return 1.0 - len(ta & tb) / len(ta | tb)


def field_disagreement(spec: FieldSpec, a: str, b: str) -> float:
    """0.0 = agree, 1.0 = disagree; strings score in between on partial overlap."""
    na, nb = normalize(spec, a), normalize(spec, b)
    if na == nb:
        return 0.0
    if spec.type == "string":
        return _token_jaccard_distance(na, nb)
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
