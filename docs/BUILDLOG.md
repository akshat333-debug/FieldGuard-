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

## Iteration 15 — figure refresh: three models, n=50
- `examples/figure.py` now reads the three described t=0.5 results
  (`sroie_50_desc_*`), one point per model, verify-everything reference line.
  Figure and README tell the same story from the same runs: 0.860/61% saved ->
  0.720/56% -> 0.035/0%. Palette re-validated for 3 categorical slots (direct
  labels cover the sub-3:1 aqua/yellow). Full threshold sweep at n=50 skipped
  deliberately — the n=15 sweeps showed the knob flat above default.

## Iteration 16 — second real benchmark: Kleister-NDA (contracts)
- Dataset: Kleister-NDA dev set (applicaai) — real NDA contracts, OCR text_best,
  gold key=value. Kept single-valued fields (effective_date, jurisdiction, term);
  multi-valued `party` out of scope for a flat schema. 26/83 docs carry all three.
  `examples/convert_kleister.py` + `datasets/kleister_nda.schema.json`.
- Long docs (median ~16k chars) vs 4096-token local context: converter keeps
  head + tail + keyword windows around governing-law/term clauses (WINDOW=700,
  merged). Naive head+tail alone CUT the governing-law clause from most docs —
  first run scored jurisdiction 13/26 wrong with 'None'/'US' answers; clause
  windows fixed coverage to 26/26 docs and lifted qwen2.5:3b constrained
  0.615 -> 0.885.
- Robustness fix real data forced: tinyllama emitted unparseable constrained
  JSON on a contract and CRASHED the run — `extract_constrained` now degrades
  to all-empty fields (-> auto-flag -> verify) instead of raising. Test added.
- Normalization gaps contracts exposed: spelled-out numbers ("two years" ==
  "2 years" via word map) and legalese dates ("30th day of April, 2009" —
  ordinal-day strip + comma-free format list). Tests added.

## Iteration 17 — split resolution flip: arbiter-wins was damaging accuracy
- Evidence (both real benchmarks): on a three-way split the arbiter answer won
  by design, but real arbiter answers are refusals ("None", "not provided",
  "US state") or cruft often enough that verification DAMAGED accuracy —
  Kleister 3b final 0.846 < constrained 0.885; SROIE 1.5b regression in
  iteration 13 (partially) the same mechanism.
- Change: three-way split now KEEPS the constrained value (source "split-kept",
  confidence low). Rationale: constraint corruption is rare (~5%); an
  uncorroborated flag shouldn't overwrite production output, only mark it.
- Kleister rerun: 3b final 0.846 -> 0.885 (verification damage zero),
  1.5b 0.769 -> 0.795 (residual is majority-vote agreement on wrong values —
  the documented correlated-failure limitation).
- Tests: **32/32.**

## Iteration 18 — split-kept measured everywhere; docs consistent
- SROIE-50 rerun under split-kept: 3b 0.855 (±1 field), 1.5b 0.730 (+1pt),
  tinyllama 0.005 final (the old arbiter occasionally lucked into a fix; the
  rule now honestly keeps the broken output and reports 200/200 low-confidence).
- README: SROIE table refreshed + Kleister-NDA second-domain table added;
  figure regenerated from the split-kept runs. All published numbers now come
  from one code state.

## Iteration 19 — candidate-aware arbiter: NEGATIVE RESULT, reverted
- Hypothesis: showing the arbiter the two disagreeing values (unlabeled "judge"
  mode) would fix refusal/cruft answers and the person-name majority votes.
- Measured: 1.5b SROIE-50 final UNCHANGED (0.730); 3b Kleister final DAMAGED
  0.885 -> 0.833. Trace: the judge parrots the unconstrained refusal candidate
  ("not provided") — arb==unc now forms a majority, which BYPASSES the
  split-kept protection that blind arbitration + split-kept had established.
- Reverted to the blind arbiter; regression test pins candidates OUT of the
  arbiter prompt. Judge-mode results JSONs discarded (working tree restored to
  the blind-run numbers). Design rule recorded: verification signals must stay
  independent — feeding path outputs into the arbiter correlates the votes.
- Tests: **33/33.**

## Iteration 20 — bootstrap CIs on the headline numbers
- Built: `examples/analyze.py` — doc-level bootstrap (docs are the exchangeable
  unit; fields within a doc are correlated), 10k resamples, seeded. Test pins
  determinism + bracketing. Tests 34/34.
- SROIE-50: 3b [0.810, 0.900] vs 1.5b [0.680, 0.780] — DISJOINT, the model
  separation is statistically real at n=50. tinyllama [0.000, 0.015].
- Kleister-26: 3b [0.821, 0.949] vs 1.5b [0.705, 0.872] — overlap; the
  contracts gap is suggestive only at n=26. Stated as such in README.

## Iteration 21 — optional fields: absence is structural, and a capability
- Built: `FieldSpec.required` (default True). Optional fields: absence phrases
  ("none", "not provided", ...) normalize to empty; both-paths-absent counts as
  AGREEMENT (no auto-flag); one-sided absence flags normally; the required
  both-empty broken-extractor guard is unchanged. JSON schema required list
  honors the flag. Kleister converter now keeps all 83 dev contracts (75 of 249
  gold fields legitimately absent). Tests 35/35.
- **Prompt-marker failure found and measured:** the first version put
  "[optional: answer NONE if not stated]" in the FIELDS block both extraction
  paths share. The free-form path (and the arbiter, sharing the bias) started
  lazily answering NONE for effective_dates that ARE in the document —
  NONE+NONE majorities overwrote correct constrained values. 3b n=83: final
  0.639 vs constrained 0.699; the rule fixed 13 hallucinations and destroyed
  28 correct values. Same failure family as iteration 19's judge parroting:
  instructions that correlate the paths break the disagreement signal.
- Fix: NO absence instruction in extraction prompts. Absence stays structural —
  constrained path may omit optional keys (JSON required list), free-form
  parser yields "" for missing lines; only the single-field ARBITER is told it
  may answer NONE. Regression test pins the marker out.
- **Post-fix, n=83:** 3b constrained 0.771 -> final 0.767 (damage 28 -> 12,
  near-parity), 45% calls saved, flag recall 0.988. 1.5b 0.550 -> 0.562
  (verification net-positive again), 47% saved.
- **Capability finding:** absent-gold fields answered correctly-absent: 3b
  54/75, 1.5b 6/75 — the smaller model hallucinates a value for almost every
  absent field on both paths (correlated, invisible to disagreement). Absence
  detection is a model capability, not a prompting trick; FieldGuard surfaces
  the disagreement-visible share and the rest is the documented correlated
  blind spot.
- Addendum (tinyllama n=83): answers absent for ALL 249 fields -> scores 0.301
  = exactly the gold-absence share, with only 4/249 low-confidence. On
  all-optional schemas the empty-field auto-flag no longer trips for a fully
  broken extractor — agreement-on-absence masks it. Mitigation shipped:
  `analyze.py` prints an absent-answer-rate tripwire ([!] N/N answers absent);
  README documents "keep >= 1 required field" guidance. README Kleister table
  now reports n=83.

## Iteration 22 — Kleister tradeoff figure; figure generator parameterized
- `examples/figure.py` renders one SVG per benchmark from a spec table
  (prefix, n, title, x-scale, outfile) — SROIE + Kleister-NDA now both have
  the three-model tradeoff figure. Kleister figure embedded in README with the
  all-absent artifact caveat on the tinyllama point.

## Iteration 23 — paper outline
- docs/PAPER_OUTLINE.md: full paper skeleton distilled from iterations 0-22 —
  problem, method (with the three measured resolution rules), setup, headline
  results with CIs, the three negative results unified as "don't correlate
  the paths", limitations, reproduction map.

## Iteration 24 — Kleister threshold sweep: knob live but shallow
- Sweep (t=0.3/0.5/0.75/0.9, n=40, both qwens) on the string-heavy contract
  fields — the graded band is populated here, unlike SROIE:
  - 3b: 111 -> 107 calls at t>=0.75 (flag recall 0.975 -> 0.950), final
    accuracy FLAT at 0.750 across all thresholds.
  - 1.5b: 106 -> 103 calls, recall 0.950 -> 0.925, accuracy flat at 0.567.
- Reading: raising the threshold above default trades ~4% of calls for ~2.5pt
  flag recall, and the skipped flags are repair-neutral (accuracy unchanged) —
  partial string overlaps whose verification wasn't fixing anything anyway.
- Paper line: the threshold is a shallow cost knob on real data; default 0.5
  plus the structural rules (empty auto-flag, split-kept) carries the useful
  signal. sweep.py gained --schema (optional-field sweeps need it).

## Iteration 25 — multi-valued fields: Kleister party
- Built: `FieldSpec.multi` — set-valued fields ride the existing string plumbing
  as '; '-joined values; sets materialize only in compare/metrics
  (`normalize_set`, disagreement = 1 - set-Jaccard, metric = exact set
  equality). Constrained path joins JSON arrays; prompts ask for ALL values;
  adapter infers multi from list-typed gold. New dataset
  `kleister_nda_party.jsonl` (83 docs, 4th field `party`, 1-3 values/doc).
- **Legal-suffix normalization** (party errors demanded it): tail-position
  corporate designators equate (Incorporated==Inc, Corporation==Corp,
  L.L.C.==LLC via spaced-initialism collapse). Worth +4 party docs and +1.2pt
  final on 3b. Interior words untouched ("Company Store" safe). Tests 36/36.
- **Results (n=83, 4 fields = 332):** 3b constrained 0.723 -> final 0.738
  (42% saved), CI [0.696, 0.780]; 1.5b 0.563 -> 0.572 (45% saved),
  CI [0.521, 0.620] — still disjoint. Verification net-positive with the
  hardest field in the schema.
- Party exact-set accuracy: 3b 58/83, 1.5b 54/83. Residual error decomposes:
  entity-boundary supersets (extra descriptive appendages, "State Commission"),
  name variants beyond suffix rules ("Technologies" vs "Technology"), and gold
  noise again (gold drops "First" from a company name; gold lists "Stilwell
  Group" where the document names individual funds).
- Strict exact-set is the honest headline; per-element partial credit would
  flatter it — noted for the paper's metric discussion.

## Iteration 26 — full audit: one real bug in multi-value resolution
- **Bug (was corrupting published numbers):** `resolve()` compared candidate
  values with scalar `normalize` while `flag_fields`/`metrics` used
  `normalize_set`. For multi-valued fields the scalar form is order-sensitive,
  so an arbiter that corroborated a path *in a different order* was scored a
  three-way split — keeping the wrong value AND marking it low-confidence.
  Reproduced end-to-end before fixing; `_key()` now routes multi fields to set
  equality everywhere. Regression test:
  `test_multi_value_resolution_is_order_insensitive`.
- **Re-measured party 3b (n=83).** Extraction was bit-identical (same 290
  calls, same flags, constrained 0.723), so the delta isolates the fix:
  - final accuracy **0.738 -> 0.744** (2 party values corrected)
  - low-confidence **60 -> 68**: set semantics also *refuses* false majorities
    that scalar comparison manufactured by collapsing element boundaries
    ("A B" read as equal to {"A","B"}). Those 8 fields were being reported
    confident on a bogus match; they are now correctly flagged unreliable.
  - Both directions are honesty gains: more correct values, fewer false
    confidence claims.
- **Latent bug fixed:** multi + number arbiter answers were truncated to the
  first number (`search` vs `findall`). No current dataset hits it.
- **Metric caveats documented (not silently changed):**
  1. "Corrupted" is defined as *constrained wrong AND unconstrained right*. A
     field wrong on BOTH paths is flagged (correctly — it is unreliable, and it
     is reported low-confidence) but scores as a false positive. Reported flag
     precision is a **lower bound** on operational usefulness. This is most of
     why party precision reads 0.313.
  2. Flag P/R were macro-averaged per doc only (a clean doc with one stray flag
     contributes precision 0.0). Added **micro** (corpus-pooled) alongside;
     stored results predate the fields, so future runs carry both.
- Stale docs fixed: paper outline listed multi-value as out of scope (it ships),
  test count, and a `Resolution.source` docstring value the code never emits.
  README party numbers refreshed to the post-fix run (final 0.738 -> 0.744,
  party exact-set 58 -> **60/83**).
- **1.5b party re-run: unchanged** (0.563 -> 0.572, 274 calls, 54/83 party).
  The bug required an arbiter to corroborate a path in a different element
  order, which happened only on 3b in this corpus — so the fix moved one model
  and not the other. Post-fix 3b CI [0.696, 0.780] -> [0.699, 0.786].
- **Micro-vs-macro assumption falsified by measurement.** The audit predicted
  micro-averaged flag precision would read *higher* than macro. On
  Kleister+party 1.5b it reads LOWER (micro 0.130/0.933 vs macro 0.263/0.988):
  macro lets easy documents carry equal weight to hard ones. Paper now reports
  which averaging each table uses and claims neither as canonical. Recorded
  because the wrong prediction was already written down.
## Iteration 27 — paper draft, related work, patent reality check
- `docs/PAPER.md`: full prose draft (abstract -> conclusion), written from the
  outline then **verified line-by-line against `results/`**, which caught three
  errors in the draft itself: (1) Kleister tinyllama savings sign — it SAVES
  59% via the absent artifact, not costs 59%; (2) "near-total low-confidence
  when broken" is true on SROIE (200/200) but false on Kleister (4/249, same
  artifact); (3) the micro-vs-macro prediction above.
- **Related-work pass with real citation checks — and a hit.** PromptPort
  (arXiv:2601.06151, 2026) already does per-field confidence + field-level
  override + conservative safe-override for structured extraction. Three of our
  design points have direct precedent. Recorded as precedent, not novelty; the
  surviving claim is narrower and specifically about the SIGNAL: the constraint
  manipulation itself (no trained verifier — PromptPort trains a DistilBERT —
  and no second model).
- **Patent reality check.** Granted adjacent art exists: US12032919B1
  (post-calibration of LLM confidence scoring for extracting data points from
  documents) and US12353469B1 (verification and citation for LM outputs). The
  patent path is narrower than the earlier optimistic read; any filing needs a
  professional freedom-to-operate search, not a literature search.
- Cited datasets properly (Huang et al. ICDAR 2019 SROIE; Stanisławek et al.
  arXiv:2105.05796 Kleister) and added a checked references section.

## Iteration 29 — micro P/R populated corpus-wide; determinism proven
- Re-ran all six published cells (`examples/rerun_all.sh`). **Zero drift** on
  every accuracy/cost number across both benchmarks × three models — the
  temperature-0 reproducibility claim, verified to the digit.
- Micro flag P/R now stored everywhere. Micro reads LOWER than macro in all six
  cells (pre-registered guess was "higher" — falsified, iteration 26). Table in
  PAPER.md §4.1a.
- Sharpest case: Kleister tinyllama macro precision 0.98 vs micro **0.00** — the
  all-absent model flags every field, and under strict "corrupted" nothing
  counts as corrupted, so micro precision is zero while the behavior (flag
  everything from a model that extracts nothing) is correct. Both reported.

## Iteration 28 — party figure; generator robustness
- Third tradeoff figure (`docs/tradeoff_kleister_party.svg`) for the 4-field
  variant. `examples/figure.py` now skips models a benchmark did not run
  (party has no tinyllama cell) instead of crashing on a missing file; test
  pinned. 40 tests.

- Audit self-correction: the audit first claimed the README had no party table.
  It did (§"With the multi-valued `party` field") — the initial grep matched
  only `##` headers and missed the `###` subsection, and a duplicate section
  got added before the mistake was caught. Removed. Lesson: grep for the
  content, not the heading level.
- Tests 36 -> 39.
