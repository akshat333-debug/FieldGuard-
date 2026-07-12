"""Selective re-verification: targeted single-field arbiter queries for flagged fields."""
from __future__ import annotations

import re
from dataclasses import dataclass

from .backends import Backend
from .compare import Flag, normalize
from .schemas import FieldSpec, Schema

_NUMBER = re.compile(r"[-+]?\d[\d,]*\.?\d*")


def _clean_answer(spec: FieldSpec, text: str) -> str:
    """Strip conversational cruft from a raw arbiter answer, type-aware.

    Real models pad 'value only' answers ('USD 600.45', 'The total is 54.20').
    """
    t = text.strip().strip("\"'. ")  # interleaved quotes/periods/spaces
    if spec.type == "enum" and spec.enum:
        low = t.casefold()
        for v in spec.enum:
            if v.casefold() in low:
                return v
    if spec.type in ("number", "integer"):
        m = _NUMBER.search(t)
        if m:
            return m.group(0)
    return t


@dataclass(frozen=True)
class Resolution:
    field: str
    value: str
    source: str        # "agreement" | "majority" | "arbiter"
    confident: bool


def _arbiter_query(backend: Backend, document: str, spec: FieldSpec) -> str:
    # The arbiter stays BLIND to the disagreeing values. Candidate-aware "judge"
    # prompting was measured (BUILDLOG iteration 19) and it parrots refusal
    # candidates ("not provided"), manufacturing a false majority with the
    # unconstrained path — Kleister 3b final dropped 0.885 -> 0.833. Blind +
    # split-kept is the accuracy-safe combination.
    desc = f"DESCRIPTION: {spec.description}\n" if spec.description else ""
    prompt = (
        f"From the document, what is the value of this field? "
        f"Answer with the value only, nothing else.\n"
        f"FIELD: {spec.name}\n"
        f"TYPE: {spec.type}\n"
        f"{desc}"
        f"DOCUMENT:\n{document}\n"
    )
    return backend.generate(prompt, force_json=False).strip()


def resolve(backend: Backend, document: str, schema: Schema,
            constrained: dict[str, str], flags: list[Flag]) -> dict[str, Resolution]:
    """Re-verify only flagged fields; unflagged fields pass through as agreed.

    Final value per flagged field: majority under normalized equality among
    {constrained, unconstrained, arbiter}; three-way split -> keep constrained,
    low confidence. (Arbiter-wins was the first design: real arbiters answer
    refusals/cruft often enough that it damaged accuracy on both real
    benchmarks. Constraint corruption is rare, so an uncorroborated flag keeps
    production output and only lowers confidence — BUILDLOG iteration 17.)
    """
    flagged = {f.field: f for f in flags}
    out: dict[str, Resolution] = {}
    for spec in schema.fields:
        name = spec.name
        if name not in flagged:
            out[name] = Resolution(name, constrained[name], "agreement", True)
            continue
        fl = flagged[name]
        arb = _clean_answer(spec, _arbiter_query(backend, document, spec))
        n_con, n_unc, n_arb = (normalize(spec, v) for v in
                               (fl.constrained, fl.unconstrained, arb))
        if n_arb == n_unc or n_arb == n_con:
            winner = arb if n_arb == n_unc else fl.constrained
            out[name] = Resolution(name, winner, "majority", True)
        else:
            out[name] = Resolution(name, fl.constrained, "split-kept", False)
    return out


def final_record(resolutions: dict[str, Resolution]) -> dict[str, str]:
    return {name: r.value for name, r in resolutions.items()}
