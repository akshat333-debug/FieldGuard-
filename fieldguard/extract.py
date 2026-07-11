"""Dual-path extraction: constrained (JSON-forced) and unconstrained (free-form)."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

from .backends import Backend
from .schemas import Schema


def _field_lines(schema: Schema) -> str:
    return "\n".join(f"- {f.name} ({f.type})"
                     + (f" one of {list(f.enum)}" if f.enum else "")
                     for f in schema.fields)


def _strip_fences(text: str) -> str:
    m = re.search(r"\{.*\}", text, re.S)
    return m.group(0) if m else text


def extract_constrained(backend: Backend, document: str, schema: Schema) -> dict[str, str]:
    prompt = (
        "Extract the fields below from the document. "
        "Respond with a single JSON object matching this schema, nothing else.\n"
        f"JSON SCHEMA:\n{json.dumps(schema.to_json_schema())}\n"
        f"FIELDS:\n{_field_lines(schema)}\n"
        f"DOCUMENT:\n{document}\n"
    )
    raw = backend.generate(prompt, force_json=True)
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        obj = json.loads(_strip_fences(raw))  # one repair attempt, then let it raise
    return {f.name: str(obj.get(f.name, "")) for f in schema.fields}


def extract_unconstrained(backend: Backend, document: str, schema: Schema) -> dict[str, str]:
    prompt = (
        "Read the document and answer each field on its own line as 'name: value'. "
        "Plain text only.\n"
        f"FIELDS:\n{_field_lines(schema)}\n"
        f"DOCUMENT:\n{document}\n"
    )
    raw = backend.generate(prompt, force_json=False)
    values: dict[str, str] = {}
    for line in raw.splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            values[k.strip()] = v.strip()
    return {f.name: values.get(f.name, "") for f in schema.fields}


@dataclass(frozen=True)
class DualResult:
    constrained: dict[str, str]
    unconstrained: dict[str, str]


def dual_extract(backend: Backend, document: str, schema: Schema) -> DualResult:
    return DualResult(
        constrained=extract_constrained(backend, document, schema),
        unconstrained=extract_unconstrained(backend, document, schema),
    )
