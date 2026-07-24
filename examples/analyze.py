"""Bootstrap confidence intervals over stored experiment results.

Doc-level resampling (fields within a doc are correlated — same receipt, same
model behavior — so docs are the exchangeable unit).

Run:  python3 -m examples.analyze
"""
from __future__ import annotations

import json
import pathlib
import random

from fieldguard.adapter import schema_from_json
from fieldguard.metrics import field_accuracy

ROOT = pathlib.Path(__file__).resolve().parent.parent

CELLS = (  # (results file, schema file, label)
    ("sroie_50_desc_qwen2.5_3b_n50_t0.5", "sroie.schema", "SROIE qwen2.5:3b"),
    ("sroie_50_desc_qwen2.5_1.5b_n50_t0.5", "sroie.schema", "SROIE qwen2.5:1.5b"),
    ("sroie_50_desc_tinyllama_latest_n50_t0.5", "sroie.schema", "SROIE tinyllama"),
    ("kleister_nda_desc_qwen2.5_3b_n83_t0.5", "kleister_nda.schema", "Kleister qwen2.5:3b"),
    ("kleister_nda_desc_qwen2.5_1.5b_n83_t0.5", "kleister_nda.schema", "Kleister qwen2.5:1.5b"),
    ("kleister_nda_desc_tinyllama_latest_n83_t0.5", "kleister_nda.schema", "Kleister tinyllama"),
    ("kleister_nda_party_desc_qwen2.5_3b_n83_t0.5", "kleister_nda_party.schema", "Kleister+party qwen2.5:3b"),
    ("kleister_nda_party_desc_qwen2.5_1.5b_n83_t0.5", "kleister_nda_party.schema", "Kleister+party qwen2.5:1.5b"),
)


def bootstrap_ci(per_doc: list[float], n_boot: int = 10_000,
                 seed: int = 0) -> tuple[float, float, float]:
    """(mean, lo95, hi95) by doc-level resampling."""
    rng = random.Random(seed)
    n = len(per_doc)
    mean = sum(per_doc) / n
    means = sorted(sum(rng.choices(per_doc, k=n)) / n for _ in range(n_boot))
    return mean, means[int(0.025 * n_boot)], means[int(0.975 * n_boot)]


def flag_pr(rep: dict) -> str:
    """macro (per-doc mean) vs micro (corpus-pooled) flag precision/recall.

    Micro fields are absent from results recorded before they were
    instrumented; show a dash rather than inventing a number.
    """
    macro = f"{rep['flag_precision']:.2f}/{rep['flag_recall']:.2f}"
    if not rep.get("flag_flagged"):
        return f"{macro} / --"
    micro_p = rep["flag_tp"] / rep["flag_flagged"]
    micro_r = rep["flag_tp"] / rep["flag_corrupted"] if rep["flag_corrupted"] else 1.0
    return f"{macro} / {micro_p:.2f}/{micro_r:.2f}"


def main() -> None:
    print(f"{'cell':28} {'final acc':>9}   95% CI (doc bootstrap)")
    for stem, schema_stem, label in CELLS:
        path = ROOT / "results" / f"{stem}.json"
        if not path.exists():
            print(f"{label:28} — missing {path.name}")
            continue
        res = json.loads(path.read_text())
        schema = schema_from_json(ROOT / "datasets" / f"{schema_stem}.json")
        per_doc = [field_accuracy(schema, f, g)
                   for f, g in zip(res["finals"], res["gold"])]
        mean, lo, hi = bootstrap_ci(per_doc)
        # tripwire for the all-absent artifact: a model that answers absent
        # everywhere scores the gold-absence share on optional schemas
        from fieldguard.compare import normalize
        n_fields = sum(len(schema.fields) for _ in res["finals"])
        absent = sum(1 for fin in res["finals"] for f in schema.fields
                     if not normalize(f, fin.get(f.name, "")))
        warn = f"   [!] {absent}/{n_fields} answers absent" if absent > n_fields // 2 else ""
        print(f"{label:28} {mean:>9.3f}   [{lo:.3f}, {hi:.3f}]{warn}")
        print(f"{'':28} {'flag P/R macro / micro:':>9} {flag_pr(res['report'])}")


if __name__ == "__main__":
    main()
