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

- **schemas.FieldSpec** — `name`, `type` ∈ {string, number, integer, date, enum}, optional `enum` values.
  `Schema.to_json_schema()` renders the prompt-side JSON Schema.
- **backends.Backend** — single method `generate(prompt, force_json=False) -> str`, plus `.calls`
  counter (cost accounting). Implementations:
  - `MockBackend` — offline. Reads `field: value` lines from the DOCUMENT block of the prompt
    (a "perfect extractor"), then applies a configurable per-field corruption table **only when
    `force_json=True`** — a controlled simulation of constraint-induced corruption. This gives
    tests exact knowledge of which fields are corrupted.
  - `OpenAICompatBackend` — stdlib-urllib client for any `/v1/chat/completions` endpoint
    (OpenAI, Ollama, vLLM, ...).
- **extract** — builds prompts with `DOCUMENT:` / field-list markers; constrained path sets
  `force_json=True` and parses JSON (one fence-strip retry); unconstrained path parses
  `field: value` lines.
- **compare** — type-aware normalization before equality:
  - number/integer: strip currency symbols and thousands separators → float; relative
    tolerance 1e-6 (exact intent, robust float repr).
  - date: try ISO + common formats → ISO string.
  - enum/string: casefold, strip, collapse whitespace.
  Disagreement score: 0.0 (agree) / 1.0 (disagree); strings fall back to token-Jaccard
  distance so near-matches score between.
- **verify** — for each flagged field, one targeted query ("value only"). Final value =
  majority under normalized equality among {constrained, unconstrained, arbiter};
  ties → arbiter wins, confidence marked low.
- **metrics** — field accuracy (final vs gold), corruption rate (constrained wrong ∧
  unconstrained right), flag precision/recall vs actually-corrupted set, calls used vs
  calls a full re-verification would need.
- **data** — deterministic synthetic invoices (seeded), fields: invoice_id, vendor,
  total, date, currency. Gold labels included.

## Deliberate simplifications

- `# ponytail:` comments mark shortcuts with named ceilings (e.g., date format list,
  not a full date parser; upgrade path noted inline).
- No external deps. Real-benchmark adapters (ExtractBench etc.) are a later layer —
  the pipeline only needs `(documents, gold, schema)` tuples.
