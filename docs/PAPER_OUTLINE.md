# Paper outline — FieldGuard

Working title: **"Constrained decoding corrupts values, not structure:
detecting and selectively repairing the format tax with dual-path
disagreement"**

Every number below is reproducible from `results/` + `examples/` at the
commit that introduced it (BUILDLOG has the map).

## 1. Problem
- JSON-mode / schema-forced decoding guarantees structure, not truth; a
  forced-valid `{"price": 45}` passes every check while the document says 54.
- Existing evals score schema coverage or aggregate accuracy; existing
  mitigations (two-stage generation, multi-model verification) re-process
  everything, blindly.
- Claim: per-field, black-box detection of constraint-induced corruption is
  possible from ONE extra sample — the same model unconstrained — and it makes
  verification spend proportional to how broken the extractor actually is.

## 2. Method
- Dual-path extraction (constrained + free-form) -> type-aware normalization
  (numbers/dates/strings; punctuation-insensitive; number words; legalese
  dates; time-suffix strip) -> graded per-field disagreement (0.5 + 0.5·severity;
  strings token-Jaccard) -> threshold flag -> selective single-field arbiter ->
  majority resolution.
- Resolution rules that survived measurement:
  - **split-kept**: three-way split keeps the constrained value, low
    confidence (arbiter-wins damaged accuracy on both benchmarks — §5).
  - **blind arbiter**: no candidates in the arbiter prompt (§5).
  - **structural absence**: optional fields via JSON required-list + parser
    default; no "answer NONE" in shared prompts (§5).
  - empty REQUIRED field auto-flags (broken-extractor tripwire).

## 3. Experimental setup
- Benchmarks: SROIE receipts (ICDAR 2019; 50 docs / 200 fields; gold-noise
  ceiling ≈ 0.92) and Kleister-NDA contracts (83 docs / 249 fields, 30%
  legitimately absent; clause-window truncation for 4k context).
- Models: qwen2.5:3b (capable), qwen2.5:1.5b (mid), tinyllama-1.1B (broken),
  local Ollama, temperature 0, max_tokens 512.
- Metrics: field accuracy vs gold (doc-bootstrap 95% CIs), flag P/R vs
  actually-corrupted set, LLM calls vs verify-everything baseline.

## 4. Results
- **Adaptive cost (headline)**: calls saved vs verify-everything — SROIE
  61/56/0%, Kleister 45/47/-59%* for 3b/1.5b/tinyllama; accuracy separation
  between 3b and 1.5b is CI-disjoint on both benchmarks.
- Final accuracy ≥ constrained accuracy everywhere post split-kept (damage
  eliminated); descriptions worth +3pt free (SROIE 3b).
- Broken model: all fields flagged, 199-200/200 low-confidence self-report,
  full spend — correct degradation with zero configuration.
- Blind-spot decomposition (SROIE 3b): undetected true corruption 1.5% of
  fields (near-miss strings below threshold); residual error is gold noise +
  spec ambiguity, NOT undetected constraint damage.
- Absence: capability-dependent (3b 54/75 absent-correct, 1.5b 6/75);
  *tinyllama all-absent artifact (scores the gold-absence share silently) —
  tripwire shipped, keep ≥1 required field.

## 5. Negative results (each measured, reverted, pinned by regression test)
1. **Arbiter-wins on splits**: real arbiters answer refusals/cruft; damaged
   final accuracy on both benchmarks (Kleister 3b 0.846 < constrained 0.885).
2. **Candidate-aware (judge) arbiter**: parrots the refusal candidate,
   manufactures false majorities (Kleister 3b 0.885 -> 0.833).
3. **"Answer NONE if absent" in shared prompts**: both paths lazily deny
   present values (fixed 13 hallucinations, destroyed 28 correct fields).
- Unifying lesson: **anything that correlates the two paths (or the arbiter
  with a path) breaks the disagreement signal** — the method's power is
  exactly the independence of its samples.

## 6. Limitations
- Correlated errors invisible by construction (identical misread on both
  paths; OCR-noise experiment: accuracy drops, zero flags — source-induced
  corruption is out of scope by design).
- Threshold knob mechanically live but severity distribution is bimodal on
  these benchmarks (gross-or-none); graded band unpopulated.
- Flat single-valued schemas only (Kleister `party` multi-value out of scope).
- Small-model absence hallucination is correlated -> undetectable.

## 7. Reproduction
- `python3 -m examples.convert_sroie / convert_kleister` -> JSONL slices
  (committed), `python3 -m examples.experiment --data ... --schema ...`,
  `python3 -m examples.analyze` (CIs + tripwire), `python3 -m examples.figure`.
- Zero runtime deps; 35 unit tests.
