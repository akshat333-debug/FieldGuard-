# FieldGuard Architecture

## Thesis

Constrained decoding guarantees syntactic validity but can corrupt *values*
("format tax"). The corruption signal FieldGuard exploits: **a field whose value
changes between constrained and unconstrained generation is likely corrupted by
the constraint.** Detection is per-field, black-box, and drives *selective*
re-verification — only flagged fields pay the verification cost.

## Data flow

```
document + schema
      │
      ├── extract.constrained()    → JSON-forced values
      ├── extract.unconstrained()  → free-form values
      │
      ▼
compare.flag_fields()              → per-field disagreement score, threshold → flags
      │
      ▼
verify.resolve()                   → targeted single-field re-query for flagged fields only
      │                              majority vote: constrained / unconstrained / arbiter
      ▼
final record (+ metrics.report() when gold labels exist)
```

## Module contracts

- **schemas.FieldSpec** — `name`, `type` ∈ {string, number, integer, date, enum}, optional `enum`
  values, optional `description` (flows into BOTH extraction prompts and the arbiter query —
  worth +3 points final accuracy on SROIE via entity disambiguation, see BUILDLOG 11), and
  `required` (default True), and `multi` (set-valued; canonical string form is `; `-joined).
  Optional fields may be legitimately absent, expressed **structurally**: the shared
  extraction prompts carry NO "answer NONE" marker (that instruction made both paths lazily
  deny present values — BUILDLOG 21; only the ARBITER may be told it), absence phrases
  ("none", "not provided", …) normalize to empty, and both-paths-absent counts as agreement
  instead of tripping the empty auto-flag.
  `Schema.to_json_schema()` renders the prompt-side JSON Schema (required list honors
  `required`; `multi` fields render as arrays).
- **backends.Backend** — single method `generate(prompt, force_json=False) -> str`, plus `.calls`
  counter (cost accounting). Implementations:
  - `MockBackend` — offline. Reads `field: value` lines from the DOCUMENT block of the prompt
    (a "perfect extractor"), then applies a configurable per-field corruption table **only when
    `force_json=True`** — a controlled simulation of constraint-induced corruption. This gives
    tests exact knowledge of which fields are corrupted.
  - `OpenAICompatBackend` — stdlib-urllib client for any `/v1/chat/completions` endpoint
    (OpenAI, Ollama, vLLM, ...); sends `max_tokens` (default 512 — unbounded free-form
    output blows timeouts on small local models) and retries once on socket timeout.
- **extract** — builds prompts with `DOCUMENT:` / field-list markers; constrained path sets
  `force_json=True` and parses JSON (one fence-strip retry); unconstrained path parses
  `field: value` lines.
- **compare** — type-aware normalization before equality:
  - number/integer: strip currency symbols/codes (incl. RM/MYR) and thousands separators → float.
  - date: try ISO + common formats (incl. d/m/Y) → ISO string.
  - enum/string: casefold, collapse whitespace, punctuation-insensitive (real OCR
    benchmarks differ from gold in trailing periods/commas; letter-level diffs survive).
  Disagreement score is graded: 0.0 agree; strings = token-Jaccard distance; number/date
  mismatches map to 0.5 + 0.5·severity (relative error / days-apart capped at a year),
  so every typed mismatch clears the 0.5 default while thresholds above it skip
  near-agreements. Empty required field on either path auto-flags at 1.0 (catches the
  correlated both-paths-empty failure disagreement can't see).
  `multi` fields compare as SETS (`normalize_set` over `; `-separated parts, each scalar-
  normalized); disagreement = 1 − set-Jaccard. String normalization also equates
  tail-position corporate designators (Incorporated≡Inc, L.L.C.≡LLC) and spelled-out
  small numbers (two≡2) — each rule added in response to an observed false positive.
- **verify** — for each flagged field, one targeted query ("value only"). The arbiter is
  **blind**: it never sees the disagreeing candidates (a candidate-aware judge parrots the
  refusal candidate and manufactures false majorities — BUILDLOG 19). Final value =
  majority under normalized equality among {constrained, unconstrained, arbiter};
  a three-way split is **split-kept** — keep the CONSTRAINED (production) value and mark it
  low-confidence, because trusting a lone arbiter measurably damaged accuracy (BUILDLOG 17).
  Equality here must match compare/metrics equality: `_key()` uses `normalize_set` for
  `multi` fields, since scalar comparison is order-sensitive (audit, BUILDLOG 26).
- **metrics** — field accuracy (final vs gold; set equality for `multi`), corruption rate
  (constrained wrong ∧ unconstrained right), flag precision/recall vs actually-corrupted set
  in BOTH macro (per-doc mean) and micro (corpus-pooled) form — they differ materially and
  micro has measured *lower* on these benchmarks — plus calls used vs calls a full
  re-verification would need.
- **data** — deterministic synthetic invoices (seeded), fields: invoice_id, vendor,
  total, date, currency. Gold labels included.
- **adapter** — external datasets as JSONL (`{"document":…, "gold":{…}}`); schema inferred
  from the first record's gold types, or explicit via `schema_from_json` (adds field
  descriptions). `examples/convert_sroie.py` converts the SROIE receipt benchmark.
- **pipeline** — orchestration; `run(trace=[])` captures per-doc dual outputs + flag sets
  for error analysis (how BUILDLOG 12's blind-spot decomposition was measured).

## Deliberate simplifications

- `# ponytail:` comments mark shortcuts with named ceilings (e.g., date format list,
  not a full date parser; upgrade path noted inline).
- No external deps — including figures (`examples/figure.py` emits SVG by hand).
- The pipeline only needs `(documents, gold, schema)` tuples; adapters stay thin.
