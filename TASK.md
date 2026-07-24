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

## Done (iterations 22-28)
- 22: Kleister tradeoff figure. 23: paper outline. 24: Kleister threshold
  sweep (shallow knob, default 0.5 fine). 25: multi-valued fields (party).
- 26: **full audit** — found and fixed a real bug (multi-value resolution used
  order-sensitive scalar equality; 3b party 0.738 -> 0.744, 8 false-confident
  fields corrected), a latent multi+number truncation, stale docs; added
  micro-averaged flag P/R; micro-vs-macro prediction falsified by measurement.
- 27: paper draft (docs/PAPER.md) with numbers verified against results/;
  related-work pass found PromptPort precedent; patent reality check.
- 28: party figure + figure-generator robustness.

## Backlog
- Populate micro flag P/R corpus-wide (re-run of published cells in progress;
  `examples/rerun_all.sh`). Extraction is temp-0 deterministic, so accuracy
  numbers are expected unchanged — only the new micro fields fill in.
- Venue selection + format conversion (LaTeX) for submission.
- If pursuing a patent: professional freedom-to-operate search FIRST
  (US12032919B1 / US12353469B1 are adjacent granted art).

## Design rules (settled, don't re-litigate)
- Split-kept: three-way split keeps constrained value.
- Blind arbiter: no candidates in arbiter prompt (judge parrots).
- Structural absence: no "answer NONE" in shared prompts; arbiter only.
- Resolution equality must match compare/metrics equality (set-valued for
  multi fields) — the audit bug.
- Zero runtime deps; figures are hand-emitted SVG.
