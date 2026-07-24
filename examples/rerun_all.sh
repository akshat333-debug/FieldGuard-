#!/usr/bin/env bash
# Re-run every published cell so micro-averaged flag P/R is populated corpus-wide.
# Extraction is temperature-0 deterministic (verified: the 3b party re-run
# reproduced constrained accuracy to 16 decimal places), so accuracy numbers
# should be unchanged; only the new micro fields get filled in.
set -u
cd "$(dirname "$0")/.."

run() {  # run <dataset> <schema> <model> <n>
  echo "=== $3 on $1 (n=$4) ==="
  python3 -m examples.experiment --data "datasets/$1.jsonl" \
      --schema "datasets/$2.schema.json" --model "$3" --n "$4" 2>&1 | tail -9
}

run sroie_50        sroie             qwen2.5:3b       50
run sroie_50        sroie             qwen2.5:1.5b     50
run sroie_50        sroie             tinyllama:latest 50
run kleister_nda    kleister_nda      qwen2.5:3b       83
run kleister_nda    kleister_nda      qwen2.5:1.5b     83
run kleister_nda    kleister_nda      tinyllama:latest 83
echo "=== ALL CELLS DONE ==="
