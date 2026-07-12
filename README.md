# FieldGuard

**Black-box field-level corruption detection for selective re-verification in structured LLM extraction.**

## Problem

Constrained decoding (JSON mode, schema enforcement) guarantees *structure*, not *truth*.
A forced-valid `{"price": 45}` passes every schema check while the document says `54`.
Existing benchmarks (JSONSchemaBench, ExtractBench) score schema coverage or aggregate
accuracy; existing mitigations (two-stage generation, multi-model verification)
re-process *everything*, blindly and expensively.

## Mechanism

For each document, FieldGuard extracts **twice**:

1. **Constrained path** — schema-forced JSON output.
2. **Unconstrained path** — free-form field/value answers.

Fields where the two paths **disagree** (after type-aware normalization) are flagged as
likely constraint-corrupted, and **only those fields** are re-verified with a targeted
single-field query. Result: recover most of the lost accuracy at a fraction of the
verification cost. Pure black-box — no logits, no fine-tuning, bolts onto any stack.

## Quickstart

```bash
python3 -m examples.demo          # offline demo (mock backend, synthetic invoices)
python3 -m pytest tests/ -q      # test suite
```

Real LLM backend (any OpenAI-compatible endpoint):

```python
from fieldguard.backends import OpenAICompatBackend
backend = OpenAICompatBackend(base_url="http://localhost:11434/v1", model="llama3.1")
```

## Package layout

| Module | Role |
|---|---|
| `fieldguard/schemas.py` | Field/schema specs + JSON Schema export |
| `fieldguard/backends.py` | LLM backend protocol, mock (offline/tests), OpenAI-compatible |
| `fieldguard/extract.py` | Dual-path extraction (constrained + unconstrained) |
| `fieldguard/compare.py` | **Core**: type-aware normalization + per-field disagreement |
| `fieldguard/verify.py` | Selective re-verification of flagged fields |
| `fieldguard/metrics.py` | Corruption rate, flag precision/recall, cost accounting |
| `fieldguard/data.py` | Synthetic gold dataset (offline development) |
| `fieldguard/pipeline.py` | End-to-end orchestration |
| `fieldguard/calibrate.py` | Threshold sweep: accuracy vs verification-cost curve |
| `fieldguard/adapter.py` | JSONL loader for external datasets, schema inference |

## Real benchmark: SROIE receipts (ICDAR 2019, 50 docs / 200 fields)

Real scanned-receipt OCR text, gold company/date/address/total.
Convert once with `python3 -m examples.convert_sroie`, run with
`python3 -m examples.experiment --data datasets/sroie_50.jsonl
--schema datasets/sroie.schema.json --model <m> --n 50`.

| | qwen2.5:3b | qwen2.5:1.5b | tinyllama-1.1B |
|---|---|---|---|
| constrained accuracy | 0.820 | 0.715 | 0.005 |
| final accuracy | 0.855 | 0.730 | 0.005 |
| flag precision / recall | 0.780 / 0.950 | 0.690 / 0.970 | 0.085 / 1.0 |
| low-confidence self-report | 5/200 | 17/200 | 200/200 |
| LLM calls vs verify-everything | **-61%** | **-56%** | 0% (all flagged) |

All columns use `datasets/sroie.schema.json` field descriptions — one sentence
per field buys the capable model +3 points final accuracy at identical cost
(company errors 13→8; BUILDLOG iteration 11); the broken model is unmoved.
**Verification spend tracks model quality monotonically** — the knob nobody
has to tune: 61% → 56% → 0% saved as the extractor degrades.

Gold-noise ceiling ≈ 0.92 (SROIE gold sometimes disagrees with its own OCR text;
see BUILDLOG iteration 7). The adaptive-cost finding replicates on real data.

![Accuracy vs verification cost on SROIE](docs/tradeoff_sroie.svg)

## Second domain: Kleister-NDA contracts (26 docs / 78 fields)

Real NDA contracts (long documents — the converter keeps head + tail + keyword
windows around the governing-law/term clauses to fit a 4k local context).
Fields: effective_date, jurisdiction, term.

| | qwen2.5:3b | qwen2.5:1.5b | tinyllama-1.1B |
|---|---|---|---|
| constrained accuracy | 0.885 | 0.808 | 0.000 |
| final accuracy | 0.885 | 0.795 | 0.000 |
| flag precision / recall | 0.596 / 1.0 | 0.654 / 1.0 | 0.0 / 1.0 |
| LLM calls vs verify-everything | **-50%** | **-52%** | 0% (all flagged) |

Same adaptive-cost shape in a second domain. Contracts pushed three fixes into
the method: clause-window truncation, number-word/legalese-date normalization,
and the split-kept resolution rule (an uncorroborated flag keeps the
constrained value instead of trusting a lone arbiter answer — arbiter-wins was
measurably damaging accuracy; BUILDLOG iteration 17).

Regenerate: `python3 -m examples.sweep --data datasets/sroie_15.jsonl --model <m> --n 15
--thresholds 0.3,0.5,0.6,0.75,0.9` then `python3 -m examples.figure`.

## First real-model results (local Ollama, 8 prose invoices / 40 fields)

| | qwen2.5:3b | tinyllama-1.1B |
|---|---|---|
| constrained accuracy | 1.000 | 0.000 |
| final accuracy | 1.000 | 0.400 |
| flag precision / recall | 0.875 / 1.0 | 0.938 / 1.0 |
| low-confidence self-report | 0/40 | 37/40 |
| LLM calls vs verify-everything | **-70%** | 0% (all flagged) |

Verification spend adapts to model quality: near-zero overhead on a capable
model, full spend plus loud self-reporting on a broken one. Known limitation
(documented in `docs/BUILDLOG.md`): identical correlated errors across both
paths are invisible to disagreement by construction; the empty-field case is
auto-flagged.

**Scope delineation (OCR-noise experiment):** with smudged source text the model
misreads both paths identically — accuracy drops, zero flags fire. The dual-path
signal detects *constraint-induced* corruption specifically; *source-induced*
corruption needs a different signal. Full findings: `docs/BUILDLOG.md` iteration 6.

See `docs/ARCHITECTURE.md` for the full design and `docs/BUILDLOG.md` for the
build-test-fix-document history.
