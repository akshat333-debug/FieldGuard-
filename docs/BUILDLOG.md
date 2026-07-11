# Build Log

Loop discipline: **build → test → fix → document → commit**. One entry per iteration.

## Iteration 0 — scaffold
- Cloned empty repo, laid package skeleton, README, ARCHITECTURE, pyproject.
- Environment: Python 3.13.9, pytest 8.4.2, zero runtime deps (stdlib only).
- Decision: MockBackend simulates constraint-induced corruption via a per-field
  corruption table applied only under `force_json=True` — gives tests exact ground
  truth about which fields are corrupted, so detector recall/precision are directly
  assertable.

## Iteration 1 — schemas, backends, extraction, detector
- Built: `schemas.py`, `backends.py` (Mock + OpenAI-compatible), `extract.py`
  (dual-path), `compare.py` (normalization + disagreement + flag_fields).
- Tests: 7 — schema validation, number/date/string normalization equivalence
  ("$54.20"≡"54.2", "2026-03-14"≡"14 March 2026"), corruption isolation
  (constrained-only), fenced-JSON repair, exact flag set, clean no-flags.
- Result: **7/7 passed first run.** No fixes needed this iteration.
- Note: string near-miss ("Acme Corp" vs "Ajax Corp") scores 0.67 via token-Jaccard
  → above 0.5 default threshold → flagged. Threshold is the calibration knob.
