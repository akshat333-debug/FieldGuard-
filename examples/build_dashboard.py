"""Emit docs/dashboard.html — a self-contained inspector for stored runs.

Reads results/ + datasets/ and inlines a subset (all cell metrics, plus the
per-document dual-path trace for a sample of documents) so the page works
offline with no server and no dependencies.

Run:  python3 -m examples.build_dashboard
"""
from __future__ import annotations

import json
import pathlib

from fieldguard.adapter import load_jsonl, schema_from_json
from fieldguard.compare import field_disagreement, normalize
from fieldguard.ground import support
from fieldguard.metrics import _eq

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOCS_PER_CELL = 12

CELLS = (  # (results stem, dataset stem, schema stem, benchmark, model)
    ("sroie_50_desc_qwen2.5_3b_n50_t0.5", "sroie_50", "sroie",
     "SROIE receipts", "qwen2.5:3b"),
    ("sroie_50_desc_qwen2.5_1.5b_n50_t0.5", "sroie_50", "sroie",
     "SROIE receipts", "qwen2.5:1.5b"),
    ("sroie_50_desc_tinyllama_latest_n50_t0.5", "sroie_50", "sroie",
     "SROIE receipts", "tinyllama-1.1B"),
    ("kleister_nda_desc_qwen2.5_3b_n83_t0.5", "kleister_nda", "kleister_nda",
     "Kleister-NDA contracts", "qwen2.5:3b"),
    ("kleister_nda_desc_qwen2.5_1.5b_n83_t0.5", "kleister_nda", "kleister_nda",
     "Kleister-NDA contracts", "qwen2.5:1.5b"),
    ("kleister_nda_desc_tinyllama_latest_n83_t0.5", "kleister_nda",
     "kleister_nda", "Kleister-NDA contracts", "tinyllama-1.1B"),
    ("kleister_nda_party_desc_qwen2.5_3b_n83_t0.5", "kleister_nda_party",
     "kleister_nda_party", "Kleister-NDA + party", "qwen2.5:3b"),
    ("kleister_nda_party_desc_qwen2.5_1.5b_n83_t0.5", "kleister_nda_party",
     "kleister_nda_party", "Kleister-NDA + party", "qwen2.5:1.5b"),
)


def collect() -> list[dict]:
    cells = []
    for stem, data_stem, schema_stem, bench, model in CELLS:
        path = ROOT / "results" / f"{stem}.json"
        if not path.exists():
            continue
        res = json.loads(path.read_text())
        rep = res["report"]
        schema = schema_from_json(ROOT / "datasets" / f"{schema_stem}.schema.json")
        examples, _ = load_jsonl(ROOT / "datasets" / f"{data_stem}.jsonl",
                                 schema=schema)
        trace = res.get("trace") or []

        docs = []
        for i, (ex, final, gold) in enumerate(
                zip(examples, res["finals"], res["gold"])):
            if i >= DOCS_PER_CELL:
                break
            tr = trace[i] if i < len(trace) else {}
            flagged = set(tr.get("flagged", []))
            fields = []
            for spec in schema.fields:
                con = (tr.get("constrained") or {}).get(spec.name, "")
                unc = (tr.get("unconstrained") or {}).get(spec.name, "")
                fin = final.get(spec.name, "")
                fields.append({
                    "name": spec.name,
                    "constrained": con,
                    "unconstrained": unc,
                    "final": fin,
                    "gold": gold[spec.name],
                    "flagged": spec.name in flagged,
                    "correct": _eq(schema, spec.name, fin, gold[spec.name]),
                    "score": round(field_disagreement(spec, con, unc), 2)
                             if (con or unc) else None,
                    "grounded": round(support(spec, fin, ex.document), 2),
                    "optional": not spec.required,
                })
            docs.append({"text": ex.document[:2200], "fields": fields})

        saved = 1 - rep["llm_calls"] / rep["full_verify_calls"]
        micro_p = (rep.get("flag_tp", 0) / rep["flag_flagged"]
                   if rep.get("flag_flagged") else None)
        cells.append({
            "id": stem, "benchmark": bench, "model": model,
            "docs_n": rep["docs"], "fields_n": rep["fields_total"],
            "constrained": round(rep["constrained_acc"], 3),
            "final": round(rep["final_acc"], 3),
            "saved": round(saved, 3),
            "calls": rep["llm_calls"], "full_calls": rep["full_verify_calls"],
            "low_conf": rep["low_confidence"],
            "macro_p": round(rep["flag_precision"], 2),
            "macro_r": round(rep["flag_recall"], 2),
            "micro_p": round(micro_p, 2) if micro_p is not None else None,
            "sample": docs,
        })
    return cells


def main() -> None:
    data = collect()
    tpl = (ROOT / "examples" / "dashboard_template.html").read_text()
    html = tpl.replace("/*__DATA__*/null",
                       json.dumps(data, separators=(",", ":")))
    out = ROOT / "docs" / "dashboard.html"
    out.write_text(html)
    kb = len(html) / 1024
    print(f"dashboard -> {out}  ({kb:.0f} KB, {len(data)} cells)")


if __name__ == "__main__":
    main()
