"""Real-model experiment: run FieldGuard against an OpenAI-compatible endpoint.

Run:  python3 -m examples.experiment --model qwen2.5:3b --n 8
      (defaults target a local Ollama server)

Dumps a JSON results file under results/ for analysis.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import time
from dataclasses import asdict

from fieldguard.backends import OpenAICompatBackend
from fieldguard.data import (INVOICE_SCHEMA, add_ocr_noise, make_dataset,
                             make_hard_dataset, render_realistic)
from fieldguard.pipeline import run


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://localhost:11434/v1")
    ap.add_argument("--model", default="qwen2.5:3b")
    ap.add_argument("--n", type=int, default=8)
    ap.add_argument("--threshold", type=float, default=0.5)
    ap.add_argument("--hard", action="store_true",
                    help="distractor-salted documents (subtotal/due-date/customer)")
    ap.add_argument("--noise", type=float, default=0.0,
                    help="OCR character-noise rate, e.g. 0.06")
    ap.add_argument("--data", default=None,
                    help="external JSONL dataset (adapter shape); overrides synthetic")
    args = ap.parse_args()

    if args.data:
        from fieldguard.adapter import load_jsonl
        examples, schema = load_jsonl(args.data)
        examples = examples[:args.n]
        docs = [ex.document for ex in examples]
    elif args.hard:
        examples = make_hard_dataset(n=args.n)
        docs = [ex.document for ex in examples]
    else:
        examples = make_dataset(n=args.n)
        docs = [render_realistic(ex) for ex in examples]
    if args.noise:
        docs = [add_ocr_noise(d, rate=args.noise, seed=i)
                for i, d in enumerate(docs)]
    gold = [ex.gold for ex in examples]
    if not args.data:
        schema = INVOICE_SCHEMA

    backend = OpenAICompatBackend(base_url=args.base_url, model=args.model,
                                  api_key="ollama")
    print(f"Running {len(docs)} docs against {args.model} "
          f"(threshold {args.threshold}) ...")
    t0 = time.time()
    finals, report = run(backend, docs, schema, gold=gold,
                         threshold=args.threshold)
    elapsed = time.time() - t0

    print(f"\n{report.summary()}\nelapsed: {elapsed:.1f}s")

    out = {
        "model": args.model, "n": args.n, "threshold": args.threshold,
        "elapsed_sec": round(elapsed, 1), "report": asdict(report),
        "finals": finals, "gold": gold,
    }
    results = pathlib.Path(__file__).resolve().parent.parent / "results"
    results.mkdir(exist_ok=True)
    tag = (f"{pathlib.Path(args.data).stem}_" if args.data else "") + \
          ("hard_" if args.hard else "") + (f"noise{args.noise}_" if args.noise else "")
    path = results / f"{tag}{args.model.replace(':', '_')}_n{len(docs)}_t{args.threshold}.json"
    path.write_text(json.dumps(out, indent=2))
    print(f"results -> {path}")


if __name__ == "__main__":
    main()
