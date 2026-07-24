# Constrained decoding corrupts values, not structure: detecting and selectively repairing the format tax with dual-path disagreement

**Status:** working draft. Every number is reproducible from `results/` +
`examples/`; `docs/BUILDLOG.md` maps each to the iteration that produced it.

---

## Abstract

Schema-constrained decoding (JSON mode, grammar enforcement) has made
structurally invalid LLM output a solved problem, and in doing so has hidden a
second failure: the values inside a well-formed object can be wrong *because*
of the constraint. A forced-valid `{"total": 45}` passes every schema check
while the receipt reads 54. Existing benchmarks score schema coverage or
aggregate accuracy, and existing mitigations — two-stage generation,
multi-model verification — re-process every field blindly, paying full
verification cost regardless of where the damage is.

We show that constraint-induced value corruption is detectable **per field**,
**black-box**, from one extra sample: the same model asked the same question
without the constraint. Fields where the constrained and unconstrained paths
disagree, after type-aware normalization, are flagged and re-verified with a
single targeted query; unflagged fields cost nothing. On two real benchmarks
(SROIE receipts, Kleister-NDA contracts) and three local models, this recovers
the accuracy lost to constraint-forcing while cutting verification calls by
42–61% on capable models. The saving is not a tuned hyperparameter: it tracks
extractor quality automatically, degrading to full spend and 200/200
low-confidence self-reporting when the underlying model is broken — except in
one artifact case we characterize, where a model that refuses every field buys
agreement by answering nothing.

We also report three negative results, each measured and reverted, that share
one cause: **anything which correlates the two paths destroys the signal**. The
method's power is exactly the independence of its samples.

---

## 1. Introduction

Constrained decoding is now standard for structured extraction. It guarantees
that output parses and matches a schema. It does not guarantee that the values
are right, and recent work documents that the constraint itself can degrade
generation quality — the "format tax."

The practical consequence is a failure mode that is *worse than a crash*: a
malformed response is caught by a parser, but a well-formed response with a
wrong number flows silently into a database. In domains where structured
extraction is actually deployed — invoice processing, clinical abstraction,
contract review — this is the expensive case.

Two mitigations are in production use. Two-stage generation (reason freely,
then format) and multi-model verification (ask several models, compare) both
work, and both re-process everything. Their cost is proportional to corpus
size, not to the amount of damage actually present, which is typically a small
minority of fields.

This paper asks a narrower question: **can you tell which specific fields the
constraint damaged, without access to logits, without fine-tuning, and without
re-processing everything?**

Our contributions:

1. **A detector.** Per-field constraint-corruption detection from dual-path
   (constrained vs unconstrained) disagreement, using only API-visible text.
2. **A selective repair loop.** Only flagged fields are re-verified, with
   resolution rules validated by measurement rather than intuition.
3. **An adaptive-cost result**, replicated across two domains and three models:
   verification spend tracks extractor quality with no configuration.
4. **A clean scope statement.** We characterize exactly what the signal cannot
   see (correlated errors), with an experiment that produces the failure
   deliberately.
5. **Three negative results**, each with a regression test pinning the reverted
   behavior.

## 2. Method

### 2.1 Dual-path extraction

For each document and schema we sample twice from the *same* model:

- **Constrained path** — schema-forced JSON (`response_format`/JSON mode).
- **Unconstrained path** — free-form `name: value` lines, no schema.

Prompts are otherwise matched: identical field list, identical field
descriptions, identical document. The only manipulated variable is the
constraint.

### 2.2 Type-aware normalization

Raw string comparison would flag formatting differences as corruption. Before
comparing we canonicalize per declared type:

- **numbers** — strip currency symbols/separators (`RM 9.00` → `9`)
- **dates** — parse a fixed format list to ISO; strip time-of-day suffixes;
  handle legalese (`30th day of April, 2009` → `2009-04-30`)
- **strings** — punctuation-insensitive, whitespace-collapsed, number words
  (`two years` ≡ `2 years`), corporate-suffix equivalence
  (`Incorporated` ≡ `Inc`, `L.L.C.` ≡ `LLC`) at tail position only
- **multi-valued fields** — set semantics over `; `-separated elements

Each normalization rule was added in response to an observed false positive on
real data, not anticipated.

### 2.3 Graded disagreement

Typed mismatches map to `0.5 + 0.5·severity`, so every mismatch clears the 0.5
default threshold while thresholds in (0.5, 1.0] become a real knob:

- numbers — severity = relative error
- dates — severity = day distance, saturating at one year
- strings — token-Jaccard distance
- multi — 1 − set-Jaccard

### 2.4 Selective re-verification

Flagged fields get one targeted single-field query. The arbiter is **blind**:
it never sees the disagreeing candidates (§5.2). Resolution:

- arbiter agrees with either path → **majority**, that value, confident
- three-way split → **split-kept**: keep the *constrained* (production) value,
  mark low-confidence (§5.1)
- empty required field → auto-flag regardless of agreement (broken-extractor
  tripwire; both-paths-empty is otherwise invisible to a disagreement signal)

Optional fields are handled structurally — the JSON required-list and parser
defaults — never by asking the shared prompts to answer "NONE" (§5.3).

## 3. Experimental setup

**Benchmarks.** SROIE (ICDAR 2019 scanned receipts; 50 docs × 4 fields;
company/date/address/total; gold-noise ceiling ≈ 0.92, as SROIE gold sometimes
disagrees with its own OCR text). Kleister-NDA (83 real contracts;
effective_date/jurisdiction/term, all optional, 75/249 gold fields legitimately
absent; a fourth set-valued `party` field in the 4-field variant). Long
contracts are truncated by keyword windows around the governing-law and term
clauses to fit a 4k local context.

**Models.** qwen2.5:3b (capable), qwen2.5:1.5b (mid), tinyllama-1.1B (broken),
served locally via Ollama, temperature 0, max_tokens 512.

**Metrics.** Field accuracy vs gold with doc-level bootstrap 95% CIs (fields
within a document are correlated, so documents are the exchangeable unit);
flag precision/recall against the corrupted set; LLM calls against a
verify-everything baseline (dual extraction + one arbiter per field).

**Two metric caveats we report rather than hide.** (i) "Corrupted" is defined
narrowly as *constrained wrong AND unconstrained right* — the damage the
constraint itself caused. A field wrong on **both** paths is still flagged
(correctly: it is unreliable, and it is reported low-confidence) but scores as
a false positive. Reported flag precision is therefore a **lower bound** on
operational usefulness. (ii) Flag P/R are macro-averaged per document, so a
clean document with one stray flag contributes precision 0.0. We instrumented
micro (corpus-pooled) averaging as well, expecting it to read higher; on
Kleister+party 1.5b it reads *lower* (micro 0.130/0.933 vs macro 0.263/0.988),
because macro averaging lets easy documents with few fields carry equal weight
to hard ones. We therefore report which averaging a table uses and treat
neither as the "true" number.

## 4. Results

### 4.1 Adaptive cost (headline)

| Benchmark | qwen2.5:3b | qwen2.5:1.5b | tinyllama |
|---|---|---|---|
| SROIE — calls saved | **61%** | **56%** | 0% |
| SROIE — constrained → final | 0.820 → 0.855 | 0.715 → 0.730 | 0.005 → 0.005 |
| Kleister — calls saved | **45%** | **47%** | 59%* |
| Kleister — constrained → final | 0.771 → 0.767 | 0.550 → 0.562 | 0.301* |

Verification spend tracks extractor quality monotonically on SROIE, with no
knob to tune. On the broken model there, every field is flagged, **200/200**
are self-reported low-confidence, and full cost is paid — the correct
degradation.

The Kleister tinyllama column inverts this and is **not** a counter-example to
the mechanism but an instance of the artifact in §4.4: answering "absent"
everywhere makes both paths agree, so nothing is flagged, cost looks *low*
(59% "saved") and only 4/249 fields are marked low-confidence. Agreement
purchased by refusing to answer is indistinguishable from agreement earned by
extracting correctly — which is precisely why the tripwire exists.

Accuracy separation between 3b and 1.5b is CI-disjoint on both benchmarks
(SROIE [0.810, 0.900] vs [0.680, 0.780]; Kleister [0.715, 0.819] vs
[0.494, 0.627]), so the ordering is established, not noise.

\* tinyllama answers "absent" for all 249 Kleister fields; 0.301 is exactly the
gold-absence share, and both-paths-absent counts as agreement. This is an
artifact, detected by a shipped tripwire (§4.4), not a result.

### 4.2 Multi-valued fields

Adding the set-valued `party` field (83 docs × 4 fields = 332) keeps
verification net-positive with the hardest field in the schema: 3b
0.723 → 0.744 (42% saved), 1.5b 0.563 → 0.572 (45% saved). Party exact-set
accuracy is 60/83 for 3b. We score exact-set; per-element partial credit would
flatter these numbers.

### 4.3 Where the residual error lives

Trace decomposition on SROIE-50 (3b) shows undetected true corruption is 1.5%
of fields — near-miss strings scoring below threshold. The remaining error is
gold noise and specification ambiguity, **not** undetected constraint damage.
Field descriptions (one sentence per field in the schema file) buy the capable
model +3 points of final accuracy at identical cost; the broken model is
unmoved.

### 4.4 Absence is a capability, not a formatting question

On Kleister, 3b answers 54/75 legitimately-absent fields correctly; 1.5b
hallucinates a value for 69/75 — identically on both paths, therefore
invisible to disagreement. Fully-absent output is an artifact class of its own:
`examples/analyze.py` prints an `[!] N/N answers absent` tripwire, and
all-optional schemas should retain at least one required field, since the
empty-field auto-flag no longer guards them.

## 5. Negative results

Each was measured on real benchmarks, reverted, and pinned by a named
regression test.

### 5.1 Arbiter-wins on three-way splits

Original design: when the arbiter agrees with neither path, trust the arbiter.
Real arbiters answer with refusals and cruft often enough that this *damaged*
final accuracy on both benchmarks (Kleister 3b 0.846 final vs 0.885
constrained). Constraint corruption is rare; an uncorroborated flag should keep
production output and lower confidence instead. → **split-kept**.

### 5.2 Candidate-aware ("judge") arbiter

Showing the arbiter the two disagreeing candidates seems strictly more
informative. It parrots the refusal candidate, manufacturing a false majority
with the path it copied: Kleister 3b 0.885 → 0.833. → **blind arbiter**.

### 5.3 "Answer NONE if absent" in the shared prompts

Intended to handle optional fields. Both paths became lazy and denied values
that *were* present: it fixed 13 hallucinations while destroying 28 correct
fields. → **structural absence**; only the arbiter may phrase NONE.

### 5.4 The unifying lesson

All three failures are the same failure. Anything that correlates the two paths
— a shared instruction, a shared candidate, a shared bias — collapses the
independence the disagreement signal is built on. **The method's power is the
independence of its samples**, and every design decision must protect it.

## 6. Limitations

- **Correlated errors are invisible by construction.** If the model misreads
  the source identically on both paths, there is no disagreement to detect. We
  demonstrate this deliberately: injecting 8% OCR character noise drops
  accuracy to 0.920 while **zero flags fire**. The signal detects
  *constraint-induced* corruption; *source-induced* corruption is out of scope
  and needs a different mechanism.
- **Small-model absence hallucination** is a correlated error, hence
  undetectable (§4.4).
- **The threshold is a shallow knob** on these benchmarks. Severity is
  bimodal (gross-or-none) on receipts; on contract strings the graded band is
  populated but raising the threshold trades ~4% of calls for ~2.5 points of
  flag recall with *flat* accuracy — the skipped flags were repair-neutral.
- **Cost model.** We count LLM calls, not tokens or wall-clock. The
  unconstrained path roughly doubles extraction cost before any savings; the
  reported savings are against a verify-everything baseline, which is the
  relevant comparison for a system that has decided to verify at all.
- **Scale.** Two domains, three models, ≤83 documents per cell, one language.

## 7. Reproduction

```bash
python3 -m examples.convert_sroie      # -> datasets/sroie_50.jsonl
python3 -m examples.convert_kleister   # -> datasets/kleister_nda.jsonl
python3 -m examples.experiment --data datasets/sroie_50.jsonl \
    --schema datasets/sroie.schema.json --model qwen2.5:3b --n 50
python3 -m examples.analyze            # bootstrap CIs + artifact tripwire
python3 -m examples.figure             # tradeoff SVGs
python3 -m pytest tests/ -q            # 39 tests
```

Zero runtime dependencies; figures are hand-emitted SVG.

## 8. Related work (to expand)

- Constrained/grammar decoding: JSON mode, Outlines, Guidance, XGrammar —
  structural guarantees, no value guarantees.
- Distribution-preserving decoding: GAD/ASAp, BoostCD, draft-conditioned
  decoding — correct the *distribution*, evaluated on likelihood rather than
  extraction accuracy, and require decoder access.
- Format-degradation measurement: "The Format Tax," alignment-tax analyses —
  diagnose the damage; no deployable per-field mitigation.
- Extraction benchmarks: JSONSchemaBench (schema coverage/efficiency),
  ExtractBench (aggregate accuracy) — document-level scoring, no repair.
- Selective prediction / abstention and LLM-as-judge: our arbiter is
  deliberately *not* a judge (§5.2).

**Positioning.** Prior work measures the damage or corrects the decoder. We
predict corruption at the individual field level, black-box, and spend
verification only where the prediction fires.

## 9. Conclusion

Forcing structure does not force truth. The value damage constrained decoding
causes is detectable without decoder access, from a single extra unconstrained
sample, at the granularity of the individual field — and that granularity is
what makes selective repair affordable. The resulting system spends
verification in proportion to how unreliable the extractor actually is, which
is the behavior an operator wants and does not have to configure. Its blind
spot is precise and stated: errors the two paths share.
