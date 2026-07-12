# Active plan

## Done (iterations 7-11) — see docs/BUILDLOG.md
- 7: SROIE real benchmark (15 docs), punct-insensitive strings, backend token cap.
- 8: graded disagreement scores; knob unit-proven, severity bimodal on SROIE.
- 9: tradeoff figure (docs/tradeoff_sroie.svg, stdlib SVG).
- 10: scaled to 50 receipts; findings stable.
- 11: field descriptions -> +3 points final acc at same cost (company 13->8 wrong).

## Iteration 12 — detector blind-spot analysis (IN PROGRESS)
1. [x] pipeline `trace=` collects dual outputs + flags; experiment dumps to results JSON.
2. [ ] qwen SROIE-50 described rerun with trace (RUNNING).
3. [ ] Analyze corrupted-but-unflagged fields (recall 0.95 -> what slips): correlated
   errors by field/type. Done when: quantified in BUILDLOG, committed.

## Backlog (pick next)
- Sweep n=50 described + regenerate figure with n=50 numbers.
- Third model (mid-tier) for a 3-point adaptive-cost curve.
- tinyllama described run (README table symmetry).
- ARCHITECTURE.md staleness pass (adapter, schema files, graded scores).

## Notes / surprises
- SROIE gold noisy: ~0.92 ceiling; address field concentrates the noise.
- Descriptions help entity fields (company/total), not noise-dominated ones (address).
