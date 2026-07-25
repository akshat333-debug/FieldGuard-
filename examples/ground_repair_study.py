"""Would grounding-driven repair actually raise accuracy? Offline, no LLM calls.

Candidate rule: a value that appears nowhere in the source, on a field that may
legitimately be absent, is a fabrication -> answer absent.

This is the honest test of the grounding signal. Catching an error is worthless
if the repair rule does not fix it: under split-kept, an arbiter that answers
NONE disagrees with both fabricating paths, so the fabricated value is KEPT
(only marked low-confidence). Absence-replacement is the rule that could
actually move accuracy — so we measure it directly on stored outputs.

Run:  python3 -m examples.ground_repair_study
"""
from __future__ import annotations

import json
import pathlib

from fieldguard.adapter import load_jsonl, schema_from_json
from fieldguard.ground import support
from fieldguard.metrics import _eq

ROOT = pathlib.Path(__file__).resolve().parent.parent
THRESHOLD = 0.5

CELLS = (
    ("sroie_50_desc_qwen2.5_3b_n50_t0.5", "sroie_50", "sroie", "SROIE 3b"),
    ("sroie_50_desc_qwen2.5_1.5b_n50_t0.5", "sroie_50", "sroie", "SROIE 1.5b"),
    ("kleister_nda_desc_qwen2.5_3b_n83_t0.5", "kleister_nda", "kleister_nda",
     "Kleister 3b"),
    ("kleister_nda_desc_qwen2.5_1.5b_n83_t0.5", "kleister_nda", "kleister_nda",
     "Kleister 1.5b"),
    ("kleister_nda_party_desc_qwen2.5_3b_n83_t0.5", "kleister_nda_party",
     "kleister_nda_party", "Kleister+party 3b"),
    ("kleister_nda_party_desc_qwen2.5_1.5b_n83_t0.5", "kleister_nda_party",
     "kleister_nda_party", "Kleister+party 1.5b"),
)


def study(stem: str, data_stem: str, schema_stem: str, label: str) -> None:
    res_path = ROOT / "results" / f"{stem}.json"
    if not res_path.exists():
        print(f"{label:22} — missing")
        return
    res = json.loads(res_path.read_text())
    schema = schema_from_json(ROOT / "datasets" / f"{schema_stem}.schema.json")
    examples, _ = load_jsonl(ROOT / "datasets" / f"{data_stem}.jsonl",
                             schema=schema)

    before = after = total = 0
    fixed = broken = 0
    for ex, final, gold in zip(examples, res["finals"], res["gold"]):
        for spec in schema.fields:
            total += 1
            value = final.get(spec.name, "")
            ok_before = _eq(schema, spec.name, value, gold[spec.name])
            before += ok_before

            repaired = value
            if (not spec.required
                    and support(spec, value, ex.document) < THRESHOLD):
                repaired = ""  # unsupported on an optional field -> absent
            ok_after = _eq(schema, spec.name, repaired, gold[spec.name])
            after += ok_after
            fixed += ok_after and not ok_before
            broken += ok_before and not ok_after

    d = (after - before) / total
    print(f"{label:22} {before/total:.3f} -> {after/total:.3f} "
          f"({d:+.3f})   fixed={fixed:3}  broken={broken:3}")


def main() -> None:
    print("Grounding-driven absence repair on optional fields (offline)\n")
    print(f"{'cell':22} {'accuracy':>17}   effect")
    for cell in CELLS:
        study(*cell)


if __name__ == "__main__":
    main()
