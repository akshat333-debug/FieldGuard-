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

## Iteration 5 — external dataset adapter
- Built: `adapter.py` — JSONL loader (`{"document": ..., "gold": {...}}`) with flat
  schema inference (ISO date / numeric / string). Real benchmark files get converted
  to this shape once, upstream.
- README updated with the two-model results table.
- Tests: **21/21.**
- Next for the team: convert an ExtractBench slice to the JSONL shape, run both
  local models plus one API model, sweep thresholds (`calibrate.sweep`) for the
  accuracy/cost tradeoff figure — that's the core experiment of the paper.

## Iteration 6 — hard docs, OCR noise, real-model sweep: three findings
- Built: `make_hard_dataset` (distractors: PO number vs invoice id, Bill-To customer
  vs vendor, subtotal/tax/shipping vs total, due date vs issue date),
  `add_ocr_noise` (character smudges: 0↔O, 1↔l, 5↔S...), `examples/sweep.py`,
  `--hard` / `--noise` flags on the experiment runner. Tests 23/23.
- **Finding 1 — saturation:** qwen2.5:3b stays at 1.000 constrained accuracy even
  with distractors (10 docs / 50 fields, 70% calls saved, 1 false flag). A capable
  3B model does not exhibit measurable format-tax on flat 5-field extraction.
  Paper implication: value corruption concentrates in weaker models and harder
  schemas — the measurement target must be chosen there.
- **Finding 2 — delineation (negative result, important):** with 8% OCR noise,
  constrained accuracy drops to 0.920 but ZERO flags fire — the model misreads the
  same smudged source the same way on both paths. Dual-path disagreement detects
  CONSTRAINT-induced corruption specifically; SOURCE-induced corruption is
  invisible to it by construction. Clean scope statement for the method.
- **Finding 3 — inert knob:** threshold sweep (0.1/0.5/0.9) on tinyllama is flat:
  identical accuracy/cost at every threshold. Current disagreement is effectively
  binary (typed mismatches score exactly 1.0; empties auto-flag at 1.0). Future
  work: graded scores (e.g. relative numeric error) to make the tradeoff tunable.
- Experiment matrix now: capable-model clean (near-zero overhead), capable-model
  noisy (delineation), broken-model (detection + self-report). Results JSONs in
  `results/`.

## Iteration 7 — FIRST REAL EXTERNAL BENCHMARK: SROIE receipts
- Dataset: SROIE (ICDAR 2019 KIE task) — real scanned Malaysian receipts, gold
  fields company/date/address/total. 15 receipts pulled from the zzzDavid mirror
  (box OCR lines + key JSON), converted by new `examples/convert_sroie.py` to
  `datasets/sroie_15.jsonl` (adapter shape). Box CSV text can contain commas —
  converter splits on the first 8 only; regression test added.
- Adapter gaps real data exposed, fixed:
  1. `25/12/2018` inferred as string → added d/m/Y-ish pattern to `_infer_type`.
  2. Ringgit amounts (`RM 9.00`) not stripped by `_NUM_JUNK` → added RM|MYR.
- **Measurement-fairness fix:** first qwen2.5:3b run scored 0.700 constrained /
  0.717 final, but 12 of 17 wrong fields were punctuation/whitespace-only diffs
  ("JOHOR" vs "JOHOR.", missing comma spacing) — normalization gap, not extraction
  error. String normalize is now punctuation-insensitive (keeps letters/digits/
  &/@/-); letter-level OCR differences (D.T.Y vs D.I.Y) stay distinct. Test added.
- **Backend fix real data forced:** tinyllama free-form generation on receipt text
  ran past the 120s socket timeout (no output cap at all). `OpenAICompatBackend`
  now sends `max_tokens` (default 512) and retries once on timeout. qwen run got
  36% faster wall-clock from the cap alone (115.8s → 78.8s).
- **Results (15 receipts / 60 fields, t=0.5):**
  - qwen2.5:3b — constrained 0.833 → final 0.850, corruption 3.3%, flag P/R
    0.800/1.000, 35 vs 90 calls (**61% saved**), 0 low-confidence.
  - tinyllama-1.1B — constrained 0.000 → final 0.067, ALL 60 fields flagged,
    60/60 self-reported low-confidence, 0% saved (correct behavior: broken
    extractor gets full verification + loud alarm).
  - The synthetic-world "verification cost adapts to model quality" finding
    REPLICATES on real data.
- Residual qwen errors decompose: ~4-5 fields are benchmark gold noise (doc0 OCR
  itself reads "SDN BND" vs gold "BHD"; doc13 gold contains typos "SEITA"/"SHAN"
  where the model's answer looks MORE correct; doc2 gold address includes text
  absent from the document) → effective gold ceiling ≈ 0.92-0.93. ~4-5 are genuine
  misses: company-entity confusion on receipts with person names / multiple
  companies (doc7, doc8), one total mis-pick (100.0 vs 26.60), one address
  interpolation. Company disambiguation is the real headroom.
- Tests: **26/26.**

## Iteration 8 — graded disagreement scores: knob live, band empty on SROIE
- Built: `field_disagreement` now grades typed mismatches instead of flat 1.0 —
  numbers: 0.5 + 0.5*min(1, relative error); dates: 0.5 + 0.5*min(1, days/365);
  unparseable values stay 1.0; strings keep token-Jaccard; empty-required keeps
  the 1.0 auto-flag. Mapping floor of 0.5 preserves default-threshold behavior
  exactly (every mismatch still flags at t=0.5). Unit tests pin the ordering
  (rounding < transposition < order-of-magnitude; off-by-day < off-by-month <
  off-by-years). Tests 27/27. Sweep runner gained `--data`.
- **SROIE sweep, qwen2.5:3b (t=0.3/0.5/0.6/0.75/0.9):** knob moves BELOW default
  (t=0.3: 38 calls, flag P 0.667 — partial string overlaps get flagged) and is
  flat above (35 calls, P 0.800, acc 0.850 at 0.5-0.9): every real qwen
  disagreement is gross (score ~1.0), none land in the graded (0.5, 0.9] band.
- **SROIE sweep, tinyllama: flat at every threshold** (90 calls, all 60 fields,
  acc 0.067) — a broken extractor's fields are empty/unparseable on some path,
  so the 1.0 auto-flag saturates regardless of threshold. That is the designed
  safety behavior, and it makes the threshold irrelevant for broken models.
- Honest reading: the knob is now mechanically real (proven at unit level) but
  on this benchmark the error-severity distribution is bimodal — models are
  either right or grossly wrong. The graded band would matter for near-miss
  corruption (rounding drift, off-by-one dates); neither model produces it here.
  Claim for the paper: threshold tuning buys little on flat 4-field receipt
  extraction; the default 0.5 + empty auto-flag captures the useful signal.

## Iteration 9 — tradeoff figure
- Built: `examples/figure.py` (stdlib SVG, no plotting deps) — accuracy vs LLM
  calls from the SROIE sweep JSONs, both models, verify-everything reference
  line. Rendered to `docs/tradeoff_sroie.svg`, embedded in README. Palette
  CVD-validated (2 categorical slots, direct labels for the sub-3:1 aqua).
- The figure IS the two-model finding: qwen cluster top-left (high accuracy,
  ~60% below full verification cost), tinyllama pinned to the full-cost line at
  floor accuracy — spend adapts to model quality with no configuration.

## Iteration 10 — scale to 50 receipts: findings stable
- Extended the SROIE slice 15 -> 50 receipts (`datasets/sroie_50.jsonl`, 200 fields).
- **qwen2.5:3b:** constrained 0.815 -> final 0.830, corruption 6.5%, flag P/R
  0.800/0.953, 118 vs 300 calls (**61% saved** — identical to n=15), 5/200
  low-confidence. First recall < 1.0 sighting: a few corrupted fields slip past
  the detector at scale, consistent with correlated-error blind spot.
- **tinyllama:** constrained 0.005 -> final 0.075, all flagged, 199/200
  low-confidence, 0% saved. Unchanged.
- Every headline number moves < 2 points from the 15-doc slice: the n=15
  results were not a small-sample artifact. README table now reports n=50.
  (Tradeoff figure still renders the n=15 sweeps; sweep at n=50 not re-run —
  30 pipeline runs of local inference for an expected no-change.)

## Iteration 11 — field descriptions: cheap, targeted accuracy
- Built: `FieldSpec.description` (already in the JSON schema for the constrained
  path) now flows into the unconstrained FIELDS block and the arbiter query;
  `schema_from_json` loads an explicit schema file; `--schema` flag on the
  experiment runner (results tagged `desc_`). `datasets/sroie.schema.json`
  carries the four SROIE descriptions ("issuing business, not a person/cashier/
  customer", "final amount, not subtotal/cash/change", ...).
- **qwen2.5:3b, SROIE-50, t=0.5:** final 0.830 -> **0.860** at identical cost
  (117 vs 118 calls, still 61% saved). Per-field wrong counts: company 13 -> 8,
  total 4 -> 2, date 1 -> 0, address 16 -> 18 (address is where SROIE gold noise
  concentrates — trailing unit names, gold typos — so it doesn't respond).
- Reading: the iteration-7 company-entity confusion is largely a schema-
  specification problem, not a model-capability problem. One sentence of field
  description buys +3 points final accuracy for free. Method note for the paper:
  FieldGuard is orthogonal to prompt quality — descriptions raise both paths
  together, the detector keeps working on what remains.
- Tests: **28/28.**

## Iteration 12 — blind-spot decomposition on SROIE-50 (trace analysis)
- Built: `pipeline.run(trace=[])` collects per-doc dual outputs + flag sets;
  experiment runner stores `trace` in results JSON. Tests 29/29.
- Analysis of qwen described run (200 fields, flag recall 0.950):
  - **Missed true corruption: 3/200 (1.5%)** — all address fields where the
    constrained path dropped a "NO." prefix or appended TEL/GST cruft; the
    unconstrained path was right, but token-Jaccard distance fell below the 0.5
    threshold. These live exactly in the graded string band: t=0.3 flags them
    (the sweep's 38-call point) at a precision cost.
  - **Correlated both-paths-wrong: 11/200** — decomposes to ~7 benchmark gold
    noise (gold typos "BEJUNTAL"/"PARINDUSTRIAN"/"TED", one postcode digit, one
    gold-EMPTY total the model correctly read as 8.20) and ~4 company-boundary
    ambiguity (display name vs registered owner "OWNER BY CASTLE BLUE S/B";
    "THREE STOOGES" with/without "BISTRO & CAFE"; venture-prefix inclusion).
- Paper claim this licenses: on a real benchmark, FieldGuard's residual error is
  dominated by gold noise and specification ambiguity — NOT by undetected
  constraint corruption. True constraint damage slipping the detector is ~1.5%
  of fields, all near-miss string edits, recoverable by lowering the threshold.

## Iteration 13 — third model: cost curve is monotone; first verification regression
- Added qwen2.5:1.5b (same family, between tinyllama-1.1B and qwen2.5:3b).
- **SROIE-50 described, t=0.5:** constrained 0.715 -> final 0.695, flag P/R
  0.550/0.970, 139 vs 300 calls (54% saved), 18/200 low-confidence.
- **Cost curve, three models:** 61% saved (3b) -> 54% (1.5b) -> 0% (1.1B broken).
  Verification spend tracks model quality monotonically — the adaptive-cost
  claim now has a middle point.
- **Honest regression: final < constrained (-2 points).** Trace decomposition of
  the 11 verification-damaged fields: 6 are semantically-correct dates the
  normalizer can't credit — the free-form paths answer "14 MAR 2018 18:40"
  (date + TIME); date parsing fails on the time suffix, so the field flags, and
  unc+arbiter (who agree) outvote the correct constrained ISO date. 3 are
  majority votes for a recurring person name over the business name; 2 are
  arbiter cruft ('address', 'RM'). Fix queued: strip time-of-day before date
  parsing — removes the flag AND the damage for the 6.

## Iteration 14 — date-time normalization: regression fixed, verified
- Fix: `normalize` strips a trailing time-of-day ("14 MAR 2018 18:40",
  "2018-03-05 18:24:59", "9:05 AM") before date-format parsing. Regression
  tests added; suite 30/30.
- **1.5b rerun, SROIE-50 described:** final 0.695 -> **0.720** (now >= its
  0.715 constrained — verification helps again), flag precision 0.550 -> 0.690
  (the six false date flags are gone), 131 calls (56% saved), 17/200
  low-confidence.
- Three-model README table updated. Curve: 61% / 56% / 0% saved for
  3b / 1.5b / broken-1.1B.
- Remaining 1.5b verification damage is the recurring-person-name majority vote
  (unc + arbiter agree on the buyer name) — a genuine correlated failure of the
  weaker model, in scope for the documented dual-path limitation, not a
  measurement bug.
