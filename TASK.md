# Active plan (iterations 7+)

## Iteration 7 — real external benchmark
1. [x] Dataset: SROIE (ICDAR 2019, real Malaysian receipts, company/date/address/total). 15 receipts from zzzDavid mirror (key JSON + box OCR CSVs).
2. [x] Converted via examples/convert_sroie.py -> datasets/sroie_15.jsonl. Adapter fixes needed: dd/mm/yyyy date inference, RM/MYR currency junk. Tests 25/25.
3. [x] Runs done. qwen: 0.833->0.850, P/R 0.800/1.0, 61% saved. tinyllama: 0.000->0.067,
   all flagged, 60/60 low-conf, 0% saved. Fixes forced by real data: punct-insensitive
   string normalize, backend max_tokens=512 + timeout retry.
4. [x] BUILDLOG iteration 7 + README SROIE table done. Tests 26/26. Committing.

## Iteration 8 — graded disagreement scoring
5. [ ] Read compare.py; add graded scores (relative numeric error, date distance, keep string Jaccard). Empty-required stays 1.0. Done when: unit tests for graded scores pass.
6. [ ] Re-sweep thresholds on weak model + real data. Done when: curve non-flat (or documented why still flat).
7. [ ] BUILDLOG entry, commit.

## Figure
8. [ ] Accuracy vs verification-cost figure from sweep results (read dataviz skill first). Done when: figure in results/, referenced in README.

## Notes / surprises
- SROIE gold vs OCR text mismatch exists IN THE BENCHMARK: doc0 OCR says "SDN BND",
  gold says "SDN BHD" — gold ceiling < 1.0 even for perfect extraction. Report as such.
- Iteration 8 graded-score design: non-equal typed values map to 0.5 + 0.5*severity
  (numbers: relative error; dates: days-apart/365, capped). Keeps default t=0.5
  behavior identical (every typed mismatch still >= 0.5), makes t in (0.5, 1.0]
  a real knob. Empty-required stays 1.0.
