"""Selective prediction: does FieldGuard's confidence actually rank errors last?

The pipeline's end product is not only a repaired record — it is a per-field
confidence score (``fieldguard/confidence.py``) meant to let a consumer keep the
top-k% most trustworthy fields and route the rest to a human. This study
measures that claim with the standard selective-prediction instruments:

    risk–coverage curve   accept fields in descending confidence; at each
                          coverage level, what error rate did you accept?
    AURC                  area under that curve (lower = better ranking)

Baselines, all computable from the same stored run (zero LLM calls):

    random        expected flat curve at the overall error rate — AURC equals
                  the final error rate; any signal must beat this
    flag-only     two bands: unflagged (accept first), flagged
    support-only  grounding score alone
    combined      the shipped confidence = resolution band x support

Needs results files whose trace carries per-field confidence/support/resolution
(runs made after the confidence upgrade). Run:  python3 -m examples.risk_coverage
"""
from __future__ import annotations

import json
import pathlib

from fieldguard.adapter import load_jsonl, schema_from_json
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


def aurc(fields: list[tuple[float, bool]]) -> float:
    """Area under risk–coverage: fields = [(score, wrong)], higher score first.

    Ties broken by corpus order (stable sort) — deterministic, and it does not
    let the evaluation peek at correctness inside a tie band.
    """
    ranked = sorted(fields, key=lambda t: -t[0])
    errs = 0
    area = 0.0
    for i, (_, wrong) in enumerate(ranked, 1):
        errs += wrong
        area += errs / i
    return area / len(ranked)


def study(stem: str, data_stem: str, schema_stem: str, label: str) -> str | None:
    res_path = ROOT / "results" / f"{stem}.json"
    if not res_path.exists():
        return f"{label:22} — missing {res_path.name}"
    res = json.loads(res_path.read_text())
    trace = res.get("trace") or []
    if not trace or "confidence" not in trace[0]:
        return (f"{label:22} — trace has no per-field confidence "
                "(re-run the cell after the confidence upgrade)")
    schema = schema_from_json(ROOT / "datasets" / f"{schema_stem}.schema.json")
    examples, _ = load_jsonl(ROOT / "datasets" / f"{data_stem}.jsonl",
                             schema=schema)

    combined: list[tuple[float, bool]] = []
    flag_only: list[tuple[float, bool]] = []
    support_only: list[tuple[float, bool]] = []
    for t, final, gold in zip(trace, res["finals"], res["gold"]):
        flagged = set(t["flagged"])
        for spec in schema.fields:
            wrong = not _eq(schema, spec.name, final.get(spec.name, ""),
                            gold[spec.name])
            combined.append((t["confidence"][spec.name], wrong))
            flag_only.append((0.0 if spec.name in flagged else 1.0, wrong))
            support_only.append((t["support"][spec.name], wrong))

    n = len(combined)
    err = sum(w for _, w in combined) / n  # random-order AURC == error rate
    a_comb, a_flag, a_sup = aurc(combined), aurc(flag_only), aurc(support_only)
    best = min(a_flag, a_sup)
    verdict = ("combined BEST" if a_comb < best
               else "single signal suffices" if a_comb <= best + 1e-9
               else "combined WORSE — investigate")
    return (f"{label:22} err={err:.3f}  AURC random={err:.3f} "
            f"flag={a_flag:.3f} support={a_sup:.3f} "
            f"combined={a_comb:.3f}   {verdict}")


def main() -> None:
    print("Risk–coverage of per-field confidence (lower AURC = errors ranked "
          "last)\n")
    for cell in CELLS:
        line = study(*cell)
        if line:
            print(line)
    print("\nAURC = mean over acceptance prefixes of the error rate accepted "
          "so far.\nRandom ordering scores the overall error rate; a perfect "
          "ranking pushes\nevery error to the end.")


if __name__ == "__main__":
    main()
