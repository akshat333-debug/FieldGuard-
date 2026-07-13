# Active plan

## Done (iterations 7-21) — full history in docs/BUILDLOG.md
- 7-10: SROIE benchmark (n=50), normalization + backend fixes, figure, scale-up.
- 11-12: field descriptions (+3pt free), trace capture, blind-spot decomposition.
- 13-15: qwen2.5:1.5b third model, monotone cost curve, date-time fix, figure v2.
- 16-18: Kleister-NDA contracts, clause-window truncation, crash robustness,
  split-kept resolution rule (arbiter-wins damaged accuracy).
- 19: judge arbiter — measured NEGATIVE, reverted (parrots refusals).
- 20: doc-bootstrap CIs (examples/analyze.py).
- 21: optional fields / structural absence (n=83); lazy-NONE prompt failure
  found + fixed; all-absent artifact tripwire.

## Done (iterations 22-25)
- 22: Kleister tradeoff figure (docs/tradeoff_kleister.svg).
- 23: paper outline (docs/PAPER_OUTLINE.md).
- 24: Kleister threshold sweep — shallow cost knob, default 0.5 fine.
- 25: multi-valued fields (party, exact-set metric) + legal-suffix
  normalization; verification net-positive on the 4-field schema.

## Backlog
- Paper draft (full prose) from PAPER_OUTLINE.md.
- Optional: partial-credit multi-value metric for the paper's metric discussion.

## Design rules (settled, don't re-litigate)
- Split-kept: three-way split keeps constrained value.
- Blind arbiter: no candidates in arbiter prompt (judge parrots).
- Structural absence: no "answer NONE" in shared prompts; arbiter only.
- Zero runtime deps; figures are hand-emitted SVG.
