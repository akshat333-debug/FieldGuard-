"""Threshold sweep against a real model: the accuracy/cost tradeoff figure.

Run:  python3 -m examples.sweep --model tinyllama:latest --n 6
"""
from __future__ import annotations

import argparse
import json
import pathlib
from dataclasses import asdict

from fieldguard.backends import OpenAICompatBackend
from fieldguard.calibrate import render_table, sweep
from fieldguard.data import INVOICE_SCHEMA, make_dataset, render_realistic


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://localhost:11434/v1")
    ap.add_argument("--model", default="tinyllama:latest")
    ap.add_argument("--n", type=int, default=6)
    ap.add_argument("--thresholds", default="0.1,0.5,0.9")
    ap.add_argument("--data", default=None,
                    help="external JSONL dataset (adapter shape); overrides synthetic")
    ap.add_argument("--schema", default=None,
                    help="explicit schema JSON (descriptions/optional); else inferred")
    args = ap.parse_args()

    if args.data:
        from fieldguard.adapter import load_jsonl, schema_from_json
        explicit = schema_from_json(args.schema) if args.schema else None
        examples, schema = load_jsonl(args.data, schema=explicit)
        examples = examples[:args.n]
        docs = [ex.document for ex in examples]
    else:
        schema = INVOICE_SCHEMA
        examples = make_dataset(n=args.n)
        docs = [render_realistic(ex) for ex in examples]
    gold = [ex.gold for ex in examples]
    thresholds = tuple(float(t) for t in args.thresholds.split(","))

    def factory():
        return OpenAICompatBackend(base_url=args.base_url, model=args.model,
                                   api_key="ollama")

    print(f"Sweeping {thresholds} on {args.model}, {args.n} docs ...")
    points = sweep(factory, docs, schema, gold, thresholds=thresholds)
    print(render_table(points))

    results = pathlib.Path(__file__).resolve().parent.parent / "results"
    results.mkdir(exist_ok=True)
    tag = f"{pathlib.Path(args.data).stem}_" if args.data else ""
    path = results / f"sweep_{tag}{args.model.replace(':', '_')}_n{len(docs)}.json"
    path.write_text(json.dumps([asdict(p) for p in points], indent=2))
    print(f"results -> {path}")


if __name__ == "__main__":
    main()
