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
    args = ap.parse_args()

    examples = make_dataset(n=args.n)
    docs = [render_realistic(ex) for ex in examples]
    gold = [ex.gold for ex in examples]
    thresholds = tuple(float(t) for t in args.thresholds.split(","))

    def factory():
        return OpenAICompatBackend(base_url=args.base_url, model=args.model,
                                   api_key="ollama")

    print(f"Sweeping {thresholds} on {args.model}, {args.n} docs ...")
    points = sweep(factory, docs, INVOICE_SCHEMA, gold, thresholds=thresholds)
    print(render_table(points))

    results = pathlib.Path(__file__).resolve().parent.parent / "results"
    results.mkdir(exist_ok=True)
    path = results / f"sweep_{args.model.replace(':', '_')}_n{args.n}.json"
    path.write_text(json.dumps([asdict(p) for p in points], indent=2))
    print(f"results -> {path}")


if __name__ == "__main__":
    main()
