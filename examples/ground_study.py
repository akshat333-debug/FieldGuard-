"""Offline study: does source grounding catch errors disagreement missed?

Uses ONLY stored results + the source documents — no LLM calls. For every field
in every stored run we ask two questions:

    was the final value wrong (vs gold)?
    would the grounding signal have flagged it?

The population that matters is the blind spot: fields the pipeline reported as
CONFIDENT (agreement or corroborated majority) but got wrong. Grounding is
useful exactly to the extent it fires there, and harmful to the extent it fires
on confident-correct fields.

Run:  python3 -m examples.ground_study
"""
from __future__ import annotations

import json
import pathlib

from fieldguard.adapter import load_jsonl, schema_from_json
from fieldguard.ground import support
from fieldguard.metrics import _eq

ROOT = pathlib.Path(__file__).resolve().parent.parent

CELLS = (  # (results stem, dataset stem, schema stem, label)
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

THRESHOLD = 0.5


def study(stem: str, data_stem: str, schema_stem: str, label: str) -> None:
    res_path = ROOT / "results" / f"{stem}.json"
    if not res_path.exists():
        print(f"{label:22} — missing {res_path.name}")
        return
    res = json.loads(res_path.read_text())
    schema = schema_from_json(ROOT / "datasets" / f"{schema_stem}.schema.json")
    examples, _ = load_jsonl(ROOT / "datasets" / f"{data_stem}.jsonl",
                             schema=schema)

    caught = missed = false_alarm = clean = 0
    for ex, final, gold in zip(examples, res["finals"], res["gold"]):
        for spec in schema.fields:
            value = final.get(spec.name, "")
            wrong = not _eq(schema, spec.name, value, gold[spec.name])
            fires = support(spec, value, ex.document) < THRESHOLD
            if wrong and fires:
                caught += 1
            elif wrong:
                missed += 1
            elif fires:
                false_alarm += 1
            else:
                clean += 1

    wrong_total = caught + missed
    correct_total = false_alarm + clean
    rec = caught / wrong_total if wrong_total else 0.0
    fpr = false_alarm / correct_total if correct_total else 0.0
    prec = caught / (caught + false_alarm) if (caught + false_alarm) else 0.0
    print(f"{label:22} wrong={wrong_total:4}  caught={caught:4} ({rec:.0%})"
          f"   false alarms={false_alarm:4} ({fpr:.0%} of correct)"
          f"   precision={prec:.2f}")


def gate(stem: str, data_stem: str, schema_stem: str, label: str) -> None:
    """The runtime gate: ungrounded rate, computed WITHOUT gold labels.

    This is the statistic an operator can actually observe in production to
    decide whether grounding repair is worth enabling. It is a deterministic
    function of (final values, source document), so it is recoverable offline
    from any stored run — no re-execution needed.
    """
    res_path = ROOT / "results" / f"{stem}.json"
    if not res_path.exists():
        print(f"{label:22} — missing")
        return
    res = json.loads(res_path.read_text())
    schema = schema_from_json(ROOT / "datasets" / f"{schema_stem}.schema.json")
    examples, _ = load_jsonl(ROOT / "datasets" / f"{data_stem}.jsonl",
                             schema=schema)

    ungrounded = total = 0
    for ex, final in zip(examples, res["finals"]):
        for spec in schema.fields:
            total += 1
            ungrounded += support(spec, final.get(spec.name, ""),
                                  ex.document) < THRESHOLD
    rate = ungrounded / total if total else 0.0
    band = "FABRICATING" if rate >= 0.10 else "reliable"
    print(f"{label:22} {ungrounded:>4}/{total:<5} {rate:>7.1%}   {band}")


def main() -> None:
    print("Source-grounding signal on stored outputs (no LLM calls)\n")
    print(f"{'cell':22} {'errors':>10}  {'caught by grounding':>22}"
          f"   {'cost on correct fields':>26}")
    for cell in CELLS:
        study(*cell)
    print("\nRead: 'caught' = wrong values grounding would flag; "
          "'false alarms' = correct values it would flag anyway.")

    print("\n\nRuntime gate — ungrounded rate (NO gold labels used)\n")
    print(f"{'cell':22} {'ungrounded':>10} {'rate':>7}   band")
    for cell in CELLS:
        gate(*cell)
    print("\nThe repair rule is enabled when a run lands in the FABRICATING "
          "band.\nSeparation is observed, not tuned — see PAPER.md 5a caveat.")


if __name__ == "__main__":
    main()
