"""Second signal: is an extracted value actually supported by the document?

Dual-path disagreement (compare.py) detects corruption the CONSTRAINT caused.
It is blind by construction to errors both paths share — most importantly
fabricated values, where a weak model invents a plausible answer for a field
the document never states (measured: qwen2.5:1.5b invents a value for 69/75
legitimately-absent Kleister fields, identically on both paths).

Grounding is orthogonal and equally training-free: a value that appears nowhere
in the source is unsupported regardless of how confidently both paths agree on
it. The two signals cover different failure families:

    disagreement  -> constraint-induced corruption   (paths differ)
    grounding     -> fabrication                     (paths agree, source doesn't)

Scope note: grounding cannot catch source-induced corruption (OCR noise), since
a value misread from a corrupted document *is* present in that document. That
failure family remains out of scope for both signals.
"""
from __future__ import annotations

import re

from .compare import normalize, normalize_set
from .schemas import FieldSpec

_TOKEN = re.compile(r"[^\w\s&/@-]")
_DOC_NUMBER = re.compile(r"[-+]?\d[\d,]*\.?\d*")


_STRING_SPEC = FieldSpec("_doc", "string")

# date surface forms to look for, incl. the legalese "30th day of April, 2009"
_DATE_SPANS = re.compile(
    r"\d{1,2}(?:st|nd|rd|th)?\s+day\s+of\s+\w+,?\s+\d{4}"
    r"|\d{1,2}[/-]\d{1,2}[/-]\d{2,4}"
    r"|\d{4}-\d{2}-\d{2}"
    r"|\d{1,2}\s+\w{3,9},?\s+\d{4}"
    r"|\w{3,9}\s+\d{1,2},?\s+\d{4}", re.I)


def _doc_tokens(document: str) -> set[str]:
    # normalize the DOCUMENT with the same rules used on values, so number
    # words ("two"->"2") and punctuation are handled symmetrically; a value is
    # otherwise judged ungrounded merely for being spelled differently
    tokens = set(normalize(_STRING_SPEC, document).split())
    return tokens | {t.rstrip("s") for t in tokens}  # light plural tolerance


def _doc_numbers(document: str) -> set[str]:
    out = set()
    for raw in _DOC_NUMBER.findall(document):
        cleaned = raw.replace(",", "")
        try:
            f = float(cleaned)
        except ValueError:
            continue
        out.add(str(int(f)) if f == int(f) else repr(f))
    return out


def _scalar_support(spec: FieldSpec, value: str, document: str,
                    doc_tokens: set[str], doc_numbers: set[str]) -> float:
    """0.0 = nothing in the document backs this value, 1.0 = fully supported."""
    n = normalize(spec, value)
    if not n:
        return 1.0  # absence claims nothing; nothing to ground

    if spec.type in ("number", "integer"):
        return 1.0 if n in doc_numbers else 0.0

    if spec.type == "date":
        # a date is grounded if any date-shaped span in the document
        # normalizes to the same ISO day, or the raw value appears verbatim
        if value.strip().casefold() in document.casefold():
            return 1.0
        for cand in _DATE_SPANS.findall(document):
            if normalize(spec, cand) == n:
                return 1.0
        return 0.0

    # string / enum: fraction of value tokens present in the document
    tokens = [t for t in n.split() if t]
    if not tokens:
        return 1.0
    hits = sum(1 for t in tokens if t in doc_tokens or t.rstrip("s") in doc_tokens)
    return hits / len(tokens)


def support(spec: FieldSpec, value: str, document: str) -> float:
    """Support score in [0, 1] for one extracted field value."""
    doc_tokens, doc_numbers = _doc_tokens(document), _doc_numbers(document)
    if spec.multi:
        parts = [p for p in value.split(";") if normalize(spec, p)]
        if not parts:
            return 1.0
        return min(_scalar_support(spec, p, document, doc_tokens, doc_numbers)
                   for p in parts)
    return _scalar_support(spec, value, document, doc_tokens, doc_numbers)


def ungrounded(spec: FieldSpec, value: str, document: str,
               threshold: float = 0.5) -> bool:
    """True when the document does not support the value (likely fabricated)."""
    return support(spec, value, document) < threshold
