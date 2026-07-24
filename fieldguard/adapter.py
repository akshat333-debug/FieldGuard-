"""Load external extraction datasets from JSONL.

Line format (ExtractBench-shaped; adapt upstream files to this once):
    {"document": "...", "gold": {"field": "value", ...}}

Schema is inferred from the first record's gold types unless provided:
    values parseable as numbers -> "number", ISO dates -> "date", else "string".

List-valued gold infers `multi=True` (set-valued field). # ponytail: NESTED
objects are still out of scope — inference is one level deep; write a
per-dataset adapter if a benchmark needs nesting.
"""
from __future__ import annotations

import json
import pathlib
import re

from .data import Example
from .schemas import FieldSpec, Schema

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DMY_DATE = re.compile(r"^\d{1,2}[/-]\d{1,2}[/-]\d{4}$")
_NUMBERISH = re.compile(r"^[-+]?[\d,]*\.?\d+$")


def _infer_type(value: str) -> str:
    v = value.strip()
    if _ISO_DATE.match(v) or _DMY_DATE.match(v):
        return "date"
    if _NUMBERISH.match(v):
        return "number"
    return "string"


def schema_from_json(path: str | pathlib.Path) -> Schema:
    """Explicit schema file: {"name": ..., "fields": [{"name","type","description"?,"enum"?}]}."""
    spec = json.loads(pathlib.Path(path).read_text())
    return Schema(spec["name"], tuple(
        FieldSpec(f["name"], f["type"],
                  enum=tuple(f["enum"]) if f.get("enum") else None,
                  description=f.get("description", ""),
                  required=f.get("required", True),
                  multi=f.get("multi", False))
        for f in spec["fields"]))


def load_jsonl(path: str | pathlib.Path, schema: Schema | None = None,
               name: str = "external") -> tuple[list[Example], Schema]:
    examples: list[Example] = []
    for line in pathlib.Path(path).read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        rec = json.loads(line)
        if not examples:
            first_raw = rec["gold"]  # raw types drive schema inference
        examples.append(Example(
            document=rec["document"],
            gold={k: "; ".join(str(x) for x in v) if isinstance(v, list) else str(v)
                  for k, v in rec["gold"].items()}))
    if not examples:
        raise ValueError(f"no records in {path}")
    if schema is None:
        schema = Schema(name, tuple(
            FieldSpec(k, _infer_type(str(v[0])) if isinstance(v, list) and v
                      else _infer_type(str(v)),
                      multi=isinstance(v, list))
            for k, v in first_raw.items()))
    return examples, schema
