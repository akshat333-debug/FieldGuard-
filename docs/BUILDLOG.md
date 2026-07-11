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

## Iteration 4 — calibration sweep + FIRST REAL-MODEL RUNS (Ollama)
- Built: `calibrate.py` (threshold sweep, accuracy/cost curve), `data.render_realistic`
  (prose invoices: dates as "14 March 2026", totals as "USD 9,478.23"),
  `examples/experiment.py` (CLI runner, JSON results dump).
- **Real run #1 (qwen2.5:3b) exposed two bugs the mock world couldn't:**
  1. Prompt said "as 'name: value'" — model emitted literal `name:`/`value:`
     alternating lines → parser got nothing → all 40 fields flagged → arbiter
     everywhere → one cruft answer ("USD 600.45") DEGRADED accuracy 1.000→0.975.
     Fix: unambiguous prompt (exact field names) + parser matches schema names
     case-insensitively, strips markdown cruft.
  2. `_LINE_CRUFT` regex stripped `_` (markdown italics) — ate the underscore inside
     `invoice_id` → lookup miss. Fix: keep underscores; regression test added.
  3. `_clean_answer` strip-order bug (`"INV-9".` → `INV-9"`). Fix: combined strip set.
- **Post-fix qwen2.5:3b (8 docs / 40 fields):** constrained 1.000 → final 1.000,
  flag P 0.875 / R 1.0 (1 false flag), 17 vs 56 calls (**70% saved**), 0 low-confidence.
- **tinyllama-1.1B run exposed detector blind spot:** model too weak for either path
  → both paths EMPTY → ""=="" → no disagreement → confidently-wrong passthrough
  (only 5/40 low-confidence at 0.10 accuracy). This is the correlated-failure
  limitation of any dual-path signal — now documented, partially mitigated:
  empty required field always flags (score 1.0).
- **Post-fix tinyllama:** final 0.000→0.400, **37/40 fields self-reported
  low-confidence**, 0% calls saved (everything flagged — correct behavior for a
  broken extractor).
- Paper-ready two-model finding: **verification cost adapts to model quality**
  (70% saved on capable model, full spend + loud self-report on broken one).
  Honest limitation stated: identical non-empty correlated errors remain invisible
  to dual-path disagreement by construction.
- Tests: 19/19.
