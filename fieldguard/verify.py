"""Selective re-verification: targeted single-field arbiter queries for flagged fields."""
from __future__ import annotations

from dataclasses import dataclass

from .backends import Backend
from .compare import Flag, normalize
from .schemas import Schema


@dataclass(frozen=True)
class Resolution:
    field: str
    value: str
    source: str        # "agreement" | "majority" | "arbiter"
    confident: bool


def _arbiter_query(backend: Backend, document: str, field_name: str,
                   field_type: str) -> str:
    prompt = (
        f"From the document, what is the value of this field? "
        f"Answer with the value only, nothing else.\n"
        f"FIELD: {field_name}\n"
        f"TYPE: {field_type}\n"
        f"DOCUMENT:\n{document}\n"
    )
    return backend.generate(prompt, force_json=False).strip()


def resolve(backend: Backend, document: str, schema: Schema,
            constrained: dict[str, str], flags: list[Flag]) -> dict[str, Resolution]:
    """Re-verify only flagged fields; unflagged fields pass through as agreed.

    Final value per flagged field: majority under normalized equality among
    {constrained, unconstrained, arbiter}; three-way split -> arbiter, low confidence.
    """
    flagged = {f.field: f for f in flags}
    out: dict[str, Resolution] = {}
    for spec in schema.fields:
        name = spec.name
        if name not in flagged:
            out[name] = Resolution(name, constrained[name], "agreement", True)
            continue
        fl = flagged[name]
        arb = _arbiter_query(backend, document, name, spec.type)
        n_con, n_unc, n_arb = (normalize(spec, v) for v in
                               (fl.constrained, fl.unconstrained, arb))
        if n_arb == n_unc or n_arb == n_con:
            winner = arb if n_arb == n_unc else fl.constrained
            out[name] = Resolution(name, winner, "majority", True)
        else:
            out[name] = Resolution(name, arb, "arbiter", False)
    return out


def final_record(resolutions: dict[str, Resolution]) -> dict[str, str]:
    return {name: r.value for name, r in resolutions.items()}
