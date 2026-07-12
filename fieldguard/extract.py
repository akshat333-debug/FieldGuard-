"""Dual-path extraction: constrained (JSON-forced) and unconstrained (free-form)."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

from .backends import Backend
from .schemas import Schema


def _field_lines(schema: Schema) -> str:
    # NOTE: optional fields carry no "answer NONE if absent" marker here — that
    # instruction made the free-form path lazily claim NONE for values that ARE
    # in the document, and the arbiter (sharing the bias) rubber-stamped it into
    # a false absence-majority (BUILDLOG 21: fixed 13 hallucinations, destroyed
    # 28 correct values). Absence is expressed structurally: the constrained
    # path may omit optional keys (JSON schema required list), the free-form
    # parser yields "" for missing lines, and only the ARBITER is told it may
    # answer NONE.
    return "\n".join(f"- {f.name} ({f.type})"
                     + (f" one of {list(f.enum)}" if f.enum else "")
                     + (f" — {f.description}" if f.description else "")
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
        try:
            obj = json.loads(_strip_fences(raw))  # one repair attempt
        except json.JSONDecodeError:
            obj = {}  # unparseable output -> all fields empty -> auto-flagged
    return {f.name: str(obj.get(f.name, "")) for f in schema.fields}


# strip leading bullets/quotes and bold/backtick markers; keep '_' (legit in names)
_LINE_CRUFT = re.compile(r"^[\s\-*•>]+|[*`]")


def extract_unconstrained(backend: Backend, document: str, schema: Schema) -> dict[str, str]:
    example = schema.fields[0].name
    prompt = (
        "Read the document and report every field listed below, one per line, "
        f"using the exact field name, e.g. '{example}: <value>'. Plain text only.\n"
        f"FIELDS:\n{_field_lines(schema)}\n"
        f"DOCUMENT:\n{document}\n"
    )
    raw = backend.generate(prompt, force_json=False)
    canonical = {f.name.casefold(): f.name for f in schema.fields}
    values: dict[str, str] = {}
    for line in raw.splitlines():
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        key = canonical.get(_LINE_CRUFT.sub("", k).strip().casefold())
        if key:
            values[key] = v.strip()
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
