# Active plan

## Done (iterations 7-11) — see docs/BUILDLOG.md
- 7: SROIE real benchmark (15 docs), punct-insensitive strings, backend token cap.
- 8: graded disagreement scores; knob unit-proven, severity bimodal on SROIE.
- 9: tradeoff figure (docs/tradeoff_sroie.svg, stdlib SVG).
- 10: scaled to 50 receipts; findings stable.
- 11: field descriptions -> +3 points final acc at same cost (company 13->8 wrong).

## Done (iterations 12-14)
- 12: trace capture; blind spot = 1.5% near-miss strings + gold noise/ambiguity.
- 13: qwen2.5:1.5b third point; cost curve monotone 61/56/0% saved; found
  verification regression (final < constrained).
- 14: date-time normalization fix; regression gone (0.695 -> 0.720), verified.
- Also: tinyllama described run (README symmetric), ARCHITECTURE.md catch-up.

## Backlog (pick next)
- Sweep n=50 described (3 models) + regenerate figure with n=50 numbers.
- Person-name majority-vote failure on 1.5b: arbiter prompt hardening?
- Second real benchmark (different domain) for generality claim.

## Notes / surprises
- SROIE gold noisy: ~0.92 ceiling; address field concentrates the noise.
- Descriptions help entity fields (company/total), not noise-dominated ones (address).
