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
44–61% on capable models; a second, orthogonal grounding signal adds up to
+9.2 accuracy points at zero additional calls. The saving is not a tuned
hyperparameter: it tracks extractor quality automatically, degrading to full spend and 200/200
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
6. **A second, orthogonal signal** — source grounding — that attacks the
   correlated blind spot of (4), with a gold-free runtime gate for its
   capability-dependent repair rule (§5a).
7. **A unified per-field confidence** (resolution band × source support;
   fixed constants, nothing fitted) evaluated as a selective predictor with
   risk–coverage curves and AURC against single-signal and random baselines
   (§5b).

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

**Benchmarks.** SROIE (Huang et al., ICDAR 2019 Robust Reading Challenge on
Scanned Receipts OCR and Information Extraction; 50 docs × 4 fields;
company/date/address/total; gold-noise ceiling ≈ 0.92, as SROIE gold sometimes
disagrees with its own OCR text). Kleister-NDA (Stanisławek et al., 2021,
arXiv:2105.05796 — key information extraction from long documents; 83 contracts;
effective_date/jurisdiction/term, all optional, 75/249 gold fields legitimately
absent; a fourth set-valued `party` field in the 4-field variant). Long
contracts are truncated by keyword windows around the governing-law and term
clauses to fit a 4k local context.

Both are third-party benchmarks with published gold labels, and both are used
in full rather than sampled: SROIE's 50 receipts are the first 50 in sorted
filename order of the public-label portion, and Kleister-NDA is the complete
**dev-0** split (test-A labels are withheld for the leaderboard, so dev-0 is
the largest split an independent reader can re-score). `docs/DATA.md` gives
provenance, licensing status and checksums;
`python3 -m examples.verify_datasets` re-downloads the official releases,
re-derives our files with the shipped converters and compares them
byte-for-byte, so no claim here rests on trusting our copy of the data.

**Models.** qwen2.5:3b (capable), qwen2.5:1.5b (mid), tinyllama-1.1B (broken),
served locally via Ollama, temperature 0, max_tokens 512.

**Data statement (encoding repair).** The Kleister TSV distribution encodes
newlines as literal two-character `\n` escapes. Our first converter fed them
through verbatim (≈70 fake `\n` tokens per contract, adjacent words glued
across line breaks), and every Kleister number in earlier drafts was measured
on that corrupted text. The converter now unescapes, the shipped JSONL files
were repaired (documents only, gold untouched), and all Kleister cells were
re-run on clean text; the tables below are post-repair. SROIE was unaffected.
We disclose this because the pre/post delta is itself a measurement of how
much low-level input noise moves small-model extraction.

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
| Kleister — calls saved | **47%** | **47%** | 60%* |
| Kleister — constrained → final | 0.783 → 0.779 | 0.546 → 0.550 | 0.301* |

Verification spend tracks extractor quality monotonically on SROIE, with no
knob to tune. On the broken model there, every field is flagged, **200/200**
are self-reported low-confidence, and full cost is paid — the correct
degradation.

The Kleister tinyllama column inverts this and is **not** a counter-example to
the mechanism but an instance of the artifact in §4.4: answering "absent"
everywhere makes both paths agree, so nothing is flagged at all (166 calls = exactly the
two extractions per document, 60% "saved") and 0/249 fields are marked
low-confidence. Agreement
purchased by refusing to answer is indistinguishable from agreement earned by
extracting correctly — which is precisely why the tripwire exists.

Accuracy separation between 3b and 1.5b is CI-disjoint on both benchmarks
(SROIE [0.810, 0.900] vs [0.680, 0.780]; Kleister [0.727, 0.827] vs
[0.490, 0.610]), so the ordering is established, not noise.

\* tinyllama answers "absent" for all 249 Kleister fields; 0.301 is exactly the
gold-absence share, and both-paths-absent counts as agreement. This is an
artifact, detected by a shipped tripwire (§4.4), not a result.

### 4.1a Flag precision: macro vs micro (report both)

The averaging choice moves flag precision more than any modeling decision, so
we report both. Recall is stable; precision is not.

| cell | macro P / R | micro P / R |
|---|---|---|
| SROIE 3b | 0.78 / 0.95 | 0.47 / 0.73 |
| SROIE 1.5b | 0.69 / 0.97 | 0.29 / 0.82 |
| SROIE tinyllama | 0.09 / 1.00 | 0.09 / 1.00 |
| Kleister 3b | 0.59 / 1.00 | 0.18 / 1.00 |
| Kleister 1.5b | 0.54 / 0.95 | 0.24 / 0.76 |
| Kleister tinyllama | 1.00 / 1.00* | (no flags fired) |

Two lessons. (i) Micro reads *lower* than macro everywhere — the opposite of
our pre-registered guess — because macro lets easy, few-field documents carry
equal weight to hard ones. (ii) The Kleister tinyllama row is the sharpest
illustration of vacuous defaults: on clean text the all-absent model fires
ZERO flags (agreement-on-absence everywhere), and with an empty flagged set
and an empty corrupted set both P and R default to 1.00 — perfect-looking
numbers purchased by refusing to answer anything. The operator reads them
next to the low-confidence count and the absence tripwire, not alone. (On the
pre-repair corrupted encoding this same model flagged everything instead —
macro 0.98 / micro 0.00 — either extreme is the artifact announcing itself.)

The SROIE numbers reproduced to the digit across the encoding repair (SROIE
text was untouched; temperature 0), which is the reproducibility claim made
concrete.

### 4.2 Multi-valued fields

Adding the set-valued `party` field (83 docs × 4 fields = 332) keeps
verification net-positive with the hardest field in the schema: 3b
0.720 → 0.732 (46% saved), 1.5b 0.566 → 0.575 (45% saved). Party exact-set
accuracy is 61/83 for 3b, 55/83 for 1.5b. Grounding repair (§5a) adds its free
gains on top: 3b → 0.747, 1.5b → 0.642. We score exact-set; per-element partial credit would
flatter these numbers.

### 4.3 Where the residual error lives

Trace decomposition on SROIE-50 (3b) shows undetected true corruption is 1.5%
of fields — near-miss strings scoring below threshold. The remaining error is
gold noise and specification ambiguity, **not** undetected constraint damage.
Field descriptions (one sentence per field in the schema file) buy the capable
model +3 points of final accuracy at identical cost; the broken model is
unmoved.

### 4.4 Absence is a capability, not a formatting question

On Kleister, 3b answers 53/75 legitimately-absent fields correctly; 1.5b
hallucinates a value for 72/75 — identically on both paths, therefore
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

## 5a. A second signal: source grounding

The blind spot in §6 — errors both paths share — is not uniformly opaque. It
decomposes into two families, and one of them is attackable with a second
training-free signal.

**Fabrication.** A weak extractor invents a plausible value for a field the
document never states (measured: qwen2.5:1.5b produces a value for 72 of 75
legitimately-absent Kleister fields, identically on both paths). Disagreement
cannot see this — but the *source* can: a value appearing nowhere in the
document is unsupported however confidently the paths agree. We compute a
support score per field by checking the value against the document under the
same normalization used for comparison (symmetric, so "2 years" grounds against
"two (2) years" and an ISO date grounds against "30th day of April, 2009").

**Misreading.** A value misread from a corrupted source *is* present in that
source, so grounding cannot see it either. That family remains out of scope for
both signals — the honest boundary of the whole approach.

**Detection (offline, on stored outputs, no additional LLM calls).**

| cell | errors | caught | precision | false alarms |
|---|---|---|---|---|
| SROIE 3b | 29 | 0 (0%) | — | 0 |
| SROIE 1.5b | 54 | 5 (9%) | 1.00 | 0 |
| Kleister 3b | 55 | 7 (13%) | 0.88 | 1 |
| Kleister 1.5b | 112 | 32 (29%) | 0.97 | 1 |
| Kleister+party 3b | 89 | 6 (7%) | 0.86 | 1 |
| Kleister+party 1.5b | 141 | 33 (23%) | 0.97 | 1 |

The signal is *selective*, which is the point: it fires where fabrication is
the failure mode (optional fields + a weak model) and is inert where models copy
values off a receipt (SROIE: zero catches, zero false alarms — it costs nothing
to leave on). Precision is 0.86–1.00 across all firing cells, with **exactly
one false alarm per Kleister cell** — and it is the same field every time (see
the repair table below). An earlier draft measured 0.84 with 5–9 false alarms
per cell; all but one of those were values split by the fake `\n` tokens of
the corrupted Kleister encoding (§3, data statement) and vanished with the
repair. The signal's false-alarm rate was bounded by the noise floor of its
input, not by the mechanism.

**Repair, and why it is opt-in.** Detection alone does not help: under
split-kept, an arbiter answering NONE disagrees with both fabricating paths, so
the fabricated value is kept and merely marked low-confidence. The rule that
moves accuracy is *unsupported value on an optional field → absent*:

| cell | accuracy | fixed / broken |
|---|---|---|
| Kleister 1.5b | 0.550 → **0.643** (+9.2) | 24 / 1 |
| Kleister+party 1.5b | 0.575 → **0.642** (+6.6) | 23 / 1 |
| Kleister 3b | 0.779 → **0.803** (+2.4) | 7 / 1 |
| Kleister+party 3b | 0.732 → **0.747** (+1.5) | 6 / 1 |
| SROIE (both) | unchanged (0.000) | 0 / 0 |

The rule helps every cell it fires in and breaks **exactly one field in each**
— and it is the same (document, field) pair every time, where **the gold value
does not appear in the document at all**. The
converter's clause-window truncation dropped the execution date; the model
answered `2012-09-04` with no evidence in its input and happened to match
gold; grounding judged the evidence correctly and the repair blanked it. So
across all four firing cells the rule blanked **zero** values that the source
actually supported — its entire measured cost is one label our own truncation
made unreachable. We surfaced this by running a single document through the
live app and noticing the repair had cost a correct field; the
`gold not in doc` column in `examples/ground_repair_study.py` reports it for
every cell, and `tests/test_ground_repair_scope.py` pins the boundary
(supported values untouched, required fields never blanked). An earlier draft reported it *harming* the capable model (−0.9); that
finding did not survive the encoding repair — the harm was the false alarms
above, which were input noise. We keep the rule **off by default** anyway,
because its gain is capability-dependent (+9.2 on a fabricating extractor vs
+1.8–2.8 on reliable ones, and a strict no-op on SROIE) and because one
benchmark family is not a safety proof; the gate below is the gold-free
statistic an operator can watch to decide. This is the same adaptive stance
as the cost result — the system measures its own extractor and spends
accordingly.

**The gate, and whether it decides correctly.** The ungrounded rate is a
deterministic function of (final values, source document), so it is recoverable
offline for every stored run:

| cell | ungrounded rate | repair effect | reading |
|---|---|---|---|
| SROIE 3b | 0.0% | 0.000 | nothing to repair |
| Kleister+party 3b | 2.1% | +1.5 | small, safe |
| SROIE 1.5b | 2.5% | 0.000 | nothing to repair |
| Kleister 3b | 3.2% | +2.4 | small, safe |
| Kleister+party 1.5b | 10.2% | **+6.6** | fabricating |
| Kleister 1.5b | 13.3% | **+9.2** | fabricating |

On clean text the gate's role shifts from harm-avoidance (no cell is harmed
any more) to **gain prediction**: among the cells where the repair *can* fire
(schemas with optional fields — all four Kleister cells), gain rises
monotonically with the observed ungrounded rate. SROIE's schema is
all-required, so its rule is structurally a no-op there regardless of rate
(its 2.5% ungrounded on 1.5b sits on required fields the rule never touches).
An operator watching this label-free statistic knows both whether and roughly
how much the repair will pay.

**Live end-to-end confirmation.** The table above is an offline reconstruction
over stored outputs, so we re-ran the winning cell through the full pipeline
with the rule enabled (`--ground-repair`, Kleister qwen2.5:1.5b, n=83):

| | baseline | + grounding repair |
|---|---|---|
| constrained accuracy | 0.546 | 0.546 (extraction untouched) |
| final accuracy | 0.550 | **0.643** (+9.2 pts) |
| LLM calls | 221 | **221** (repair is free — no arbiter query) |
| ungrounded rate (gate) | — | 33/249 = **13.3%** |

The live result matches the offline prediction exactly, extraction is
bit-identical (confirming the delta is the repair rule and nothing else), and
the repair costs **zero additional model calls** — it replaces a value rather
than querying for one. The gate read 13.3% with no gold labels involved.

**Honest caveat.** Six cells from one benchmark family. The monotone
rate→gain relationship is observed, not derived; the fabricating/reliable
band edges are descriptive; and a model sitting between 3.2% and 10.2% has not
been tested. We also note for the record that the pre-repair version of this
section reported the repair harming a capable model — a conclusion that
flipped when an input-encoding bug was fixed. Conclusions about *when a rule
hurts* are evidently sensitive to input noise, which is an argument for
gating on the observable statistic rather than on a model-capability prior.

## 5b. Unified confidence as a selective predictor

Every stage of the pipeline already emits an ordinal reliability cue: the
resolution band (agreement > corroborated majority > uncorroborated
split-kept) from signal 1 + the arbiter, and the support score in [0, 1] from
signal 2. We fold them into one number per field:

    confidence = band_weight × (0.5 + 0.5 · support)
    band_weight: agreement 1.0, majority 0.7, split-kept 0.3

The constants are **fixed, not fitted** — there is nothing to train and
nothing to leak — and the bands deliberately overlap: a fully grounded
majority (0.7) outranks a fully ungrounded agreement (0.5). A
ground-repaired field keeps its low pre-repair support, so the repair rule
cannot launder a detected fabrication into high confidence. We claim only
the *ranking*, not calibrated probabilities.

The claim is tested the standard selective-prediction way: accept fields in
descending confidence and plot risk (error rate accepted so far) against
coverage; AURC summarizes the curve (lower = errors ranked later). Baselines
from the same stored runs, zero extra LLM calls: **random** (AURC = the
overall error rate), **flag-only** (two bands: unflagged first), and
**support-only** (grounding score alone). `examples/risk_coverage.py`
computes all four from the per-field traces.

| cell | random | flag-only | support-only | **combined** |
|---|---|---|---|---|
| SROIE 3b | 0.145 | 0.123 | 0.141 | **0.114** |
| SROIE 1.5b | 0.270 | 0.203 | 0.245 | **0.191** |
| Kleister 3b | 0.221 | 0.143 | 0.172 | **0.129** |
| Kleister 1.5b | 0.450 | 0.313 | 0.271 | **0.240** |
| Kleister+party 3b | 0.268 | 0.191 | 0.240 | **0.160** |
| Kleister+party 1.5b | 0.425 | 0.258 | 0.318 | **0.219** |

The combined score has the lowest AURC in **6/6 cells** — and, notably,
neither component does: flag-only nearly ties it on capable models (where
disagreement is the dominant error signal) and support-only beats flag-only
on the fabricating model (where the dominant errors are correlated
fabrications no flag can see). The two signals are complementary in exactly
the way their blind-spot analysis predicts, and the fixed-weight combination
inherits the better of the two everywhere without fitting anything.

## 6. Limitations

- **Correlated errors are invisible to disagreement by construction.** If the
  model misreads the source identically on both paths, there is no
  disagreement to detect. We demonstrate this deliberately: injecting 8% OCR
  character noise drops accuracy to 0.920 while **zero flags fire**. §5a
  recovers one half of this family (fabrication) with a second signal; the
  other half (misreading a corrupted source) is out of scope for both, since a
  misread value is genuinely present in the document it was misread from.
- **The grounding gate is unvalidated.** Four informative cells suggest the
  ungrounded-rate threshold; that is a hypothesis, not a calibration.
- **The threshold is a shallow knob** on these benchmarks, and on clean text
  it is shallower still. Severity is bimodal (gross-or-none) on receipts. On
  contracts (n=40 sweep, thresholds 0.30→0.90) the capable model moves once,
  0.750 → 0.767 between 0.30 and 0.50, then is flat at 104–107 calls, and 1.5b
  buys 6% of calls (108→102) for at most 0.8 points of accuracy and 2.5 points
  of flag recall. Nobody should be tuning this; the default 0.5 is
  where we leave it, and the adaptive behavior comes from the disagreement
  rate rather than the cut-off.
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

## 8. Related work

**Constrained / grammar-guided decoding.** Willard and Louf (2023,
arXiv:2307.09702) formalize guided generation as FSM state transitions, the
basis of Outlines; Guidance, XGrammar, llama.cpp and the OpenAI/Gemini JSON
modes implement variants. JSONSchemaBench (Geng et al., 2025,
arXiv:2501.10868) evaluates six such frameworks over 10K real schemas. All
target *structural* validity; none certify values.

**Distribution-preserving decoding.** Grammar-Aligned Decoding with ASAp (Park
et al., NeurIPS 2024, arXiv:2405.21047) shows grammar-constrained decoding
distorts the model's distribution and corrects it to match the constrained
conditional; BoostCD (arXiv:2506.14901) combines constrained and unconstrained
decoding by boosting; draft-conditioned decoding conditions on a free-form
draft. These are the closest in *spirit* — BoostCD in particular also exploits
an unconstrained signal — but they operate inside the decoder (logits,
resampling), optimize likelihood rather than extraction correctness, and repair
generation uniformly rather than identifying which fields need attention.
FieldGuard needs no decoder access and produces a per-field decision.

**Measuring the format tax.** "The Format Tax" (arXiv:2604.03616) separates
prompt-level format requests from decoder-level constraints to locate the
degradation; alignment-tax analyses of constrained reflection
(arXiv:2604.06066) report similar effects. These diagnose; they do not
mitigate per field.

**Structured-extraction benchmarks.** ExtractBench (arXiv:2602.12247) and the
Structured Output Benchmark (arXiv:2604.25359) score extraction quality at the
document/aggregate level. We use benchmark *documents* (SROIE, Kleister) rather
than competing with these leaderboards, and we report a repair, not a score.

**Closest prior work — and an honest overlap.** PromptPort (arXiv:2601.06151,
2026) is a reliability layer for cross-model structured extraction that
provides **per-field confidence**, **field-level override** instead of
instance-level rejection, and a **conservative safe-override policy**. Three of
our design points therefore have direct precedent, and we do not claim them as
novel. The differences are in the confidence *signal* and the scope:

| | PromptPort | FieldGuard |
|---|---|---|
| confidence signal | trained lightweight verifier (DistilBERT) | second sample of the *same* model, constraint removed |
| extra components | trained model + canonicalization | none (no training, no second model) |
| framing | cross-model output reliability | isolates the *constraint* as the manipulated variable |
| cost model | verifier runs per field | arbiter runs only on flagged fields |

Our claim is narrower as a result: not "per-field confidence for structured
extraction" (PromptPort has that), but that **the constraint manipulation
itself is a sufficient confidence signal** — no verifier to train, no second
model to host — and that framing it causally lets us say *which kind* of
corruption is detectable (§6).

**Selective prediction, abstention, LLM-as-judge.** Our arbiter is deliberately
*not* a judge: §5.2 measures the judge formulation and shows it manufactures
false majorities.

**Patent landscape.** Granted patents already cover adjacent ground — e.g.
US12032919B1 (post-calibration of LLM confidence scoring, applied to extracting
data points from electronic documents with confidence scores) and US12353469B1
(verification and citation for language-model outputs). Any filing must be
scoped tightly to the dual-path signal and cleared by a professional
patent-database search; the searches behind this section were literature
searches, not a freedom-to-operate opinion.

## 9. References

Verified during the related-work pass; arXiv IDs checked, not merely recalled.

- Willard, B. T., Louf, R. *Efficient Guided Generation for Large Language
  Models.* arXiv:2307.09702 (2023). [Outlines / FSM-guided decoding]
- Geng, S. et al. *JSONSchemaBench: A Rigorous Benchmark of Structured Outputs
  for Language Models.* arXiv:2501.10868 (2025).
- Park, K., Wang, J., Berg-Kirkpatrick, T. et al. *Grammar-Aligned Decoding.*
  NeurIPS 2024, arXiv:2405.21047. [ASAp]
- *Combining Constrained and Unconstrained Decoding via Boosting: BoostCD.*
  arXiv:2506.14901.
- *The Format Tax.* arXiv:2604.03616.
- *From Hallucination to Structure Snowballing: The Alignment Tax of
  Constrained Decoding in LLM Reflection.* arXiv:2604.06066.
- *ExtractBench: A Benchmark and Evaluation Methodology for Complex Structured
  Extraction.* arXiv:2602.12247.
- *The Structured Output Benchmark.* arXiv:2604.25359.
- *PromptPort: A Reliability Layer for Cross-Model Structured Extraction.*
  arXiv:2601.06151 (2026). [closest prior work — §8]
- Huang, Z., Chen, K., He, J., Bai, X., Karatzas, D., Lu, S., Jawahar, C. V.
  *ICDAR 2019 Robust Reading Challenge on Scanned Receipts OCR and Information
  Extraction.* ICDAR 2019. [SROIE]
- Stanisławek, T. et al. *Kleister: Key Information Extraction Datasets
  Involving Long Documents with Complex Layouts.* arXiv:2105.05796 (2021).
- US12032919B1, *Post-calibration of large language model confidence scoring
  via combined techniques.*
- US12353469B1, *Verification and citation for language model outputs.*

## 10. Conclusion

Forcing structure does not force truth. The value damage constrained decoding
causes is detectable without decoder access, from a single extra unconstrained
sample, at the granularity of the individual field — and that granularity is
what makes selective repair affordable. The resulting system spends
verification in proportion to how unreliable the extractor actually is, which
is the behavior an operator wants and does not have to configure. Its blind
spot is precise and stated: errors the two paths share — and half of that
blind spot (fabrication) falls to a second training-free signal, source
grounding, whose free repair adds up to +9.2 points and whose gold-free gate
statistic predicts its own usefulness. Folding both signals into one
fixed-weight confidence yields the best error ranking in every measured cell
(§5b) without training anything.
