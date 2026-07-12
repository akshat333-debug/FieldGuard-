"""Field and schema specifications."""
from __future__ import annotations

from dataclasses import dataclass, field

FIELD_TYPES = {"string", "number", "integer", "date", "enum"}


@dataclass(frozen=True)
class FieldSpec:
    name: str
    type: str  # one of FIELD_TYPES
    enum: tuple[str, ...] | None = None
    description: str = ""
    required: bool = True  # optional fields may be legitimately absent

    def __post_init__(self) -> None:
        if self.type not in FIELD_TYPES:
            raise ValueError(f"unknown field type: {self.type!r}")
        if self.type == "enum" and not self.enum:
            raise ValueError(f"enum field {self.name!r} needs enum values")


@dataclass(frozen=True)
class Schema:
    name: str
    fields: tuple[FieldSpec, ...]

    def field(self, name: str) -> FieldSpec:
        for f in self.fields:
            if f.name == name:
                return f
        raise KeyError(name)

    def to_json_schema(self) -> dict:
        """JSON Schema dict for the constrained prompt."""
        type_map = {"string": "string", "number": "number", "integer": "integer",
                    "date": "string", "enum": "string"}
        props: dict[str, dict] = {}
        for f in self.fields:
            p: dict = {"type": type_map[f.type]}
            if f.type == "date":
                p["format"] = "date"
            if f.enum:
                p["enum"] = list(f.enum)
            if f.description:
                p["description"] = f.description
            props[f.name] = p
        return {
            "type": "object",
            "properties": props,
            "required": [f.name for f in self.fields if f.required],
            "additionalProperties": False,
        }
