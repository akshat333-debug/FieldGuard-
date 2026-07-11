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

## Iteration 2 — selective verifier
- Built: `verify.py` — arbiter query per flagged field only; majority vote under
  normalized equality; three-way split → arbiter value, low confidence.
- Tests: repair of corrupted fields, zero-cost clean path, three-way-split fallback.
- Result: **10/10 passed first run.**

## Iteration 3 — metrics, synthetic data, pipeline, demo
- Built: `metrics.py` (accuracy, corruption rate, flag P/R, cost vs verify-everything
  baseline), `data.py` (deterministic synthetic invoices + corruption plans +
  `PlannedMockBackend` for per-document corruption), `pipeline.py`, `examples/demo.py`.
- Fix during build: MockBackend corruption table is per-instance/global, but the
  dataset needs per-document plans → added `PlannedMockBackend` that selects the
  plan by invoice_id parsed from the prompt's DOCUMENT block.
- Tests: end-to-end (damage → detect → repair → cost), clean-run zero overhead,
  report rendering. **13/13 passed.**
- Demo (25 invoices, 15% corruption rate): constrained accuracy 0.840 → final 1.000,
  flag precision/recall 1.0/1.0, 70 calls vs 175 verify-everything (**60% saved**).
- Caveat for the paper: these are mock-world numbers (perfect extractor + controlled
  corruption). Real-model numbers come from pointing `OpenAICompatBackend` at real
  documents; flag P/R < 1.0 expected there — that's the research measurement.
