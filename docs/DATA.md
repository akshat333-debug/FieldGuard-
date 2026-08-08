# Data provenance — what every reported number is measured on

**Short version: every result in README.md and PAPER.md is measured on a public,
third-party benchmark with published gold labels. Nothing we generated
ourselves is reported as a result.** The one synthetic corpus in this repo is
labelled a smoke test in both documents and is excluded from every table.

Run this to check the claim rather than believe it:

```bash
python3 -m examples.verify_datasets
```

It downloads the official releases, re-derives our files with the shipped
converters, and compares byte-for-byte. No network access is needed to *use*
the repo — only to verify it.

## Benchmarks used for results

| corpus | source | split | size | labels |
|---|---|---|---|---|
| SROIE | ICDAR 2019 Robust Reading Challenge, Task 3 (Huang et al.) | train (public labels) | 50 receipts × 4 fields = 200 | official `key/*.json` |
| Kleister-NDA | Stanisławek et al. 2021, arXiv:2105.05796 | **dev-0** | 83 contracts × 3 or 4 fields = 249 / 332 | official `expected.tsv` |

**Split choice matters and is deliberate.** Kleister-NDA ships train (254),
dev-0 (83) and test-A (203); test-A labels are withheld for the leaderboard, so
dev-0 is the largest split whose gold is public and therefore the only one an
independent reader can re-score. We use dev-0 in full — all 83 documents, no
sampling, no filtering. SROIE test labels are likewise not public, so the 50
receipts come from the public-label portion, taken in sorted filename order
(`000`–`049`) with no cherry-picking.

### Origins

- **SROIE** — real scanned Malaysian receipts with OCR text and gold
  company/date/address/total. Retrieved via the widely used mirror
  `zzzDavid/ICDAR-2019-SROIE` (`data/key/*.json`, `data/box/*.csv`), which
  reproduces the competition release. Redistributed annotations for this
  dataset are published under **CC-BY-4.0** (e.g. the `jsdnrs/ICDAR2019-SROIE`
  dataset card); the competition site is the authoritative source of terms.
- **Kleister-NDA** — real non-disclosure agreements collected from the U.S.
  SEC **EDGAR** system (per §3 of the Kleister paper: "The NDAs were collected
  from the Electronic Data Gathering, Analysis and Retrieval system (EDGAR)").
  The underlying filings are U.S. government public records. The dataset
  repository `applicaai/kleister-nda` **does not carry an explicit LICENSE
  file** — we state this plainly rather than imply a permission that was never
  granted. We redistribute only the derived, truncated JSONL for
  reproducibility; anyone reusing it should go to the upstream repository for
  terms.

## What "derived" means (and why the derivation is checkable)

Neither benchmark ships in the `{"document":…, "gold":{…}}` shape this pipeline
consumes, so each is converted once:

- `examples/convert_sroie.py` — joins the OCR text column of `box/NNN.csv` in
  file order into a single document; gold is `key/NNN.json` verbatim.
- `examples/convert_kleister.py` — unescapes the literal `\n`/`\t` sequences
  the upstream TSV uses (see below), then, for documents longer than 4500
  characters, keeps head (3000) + tail (1500) + keyword windows around the
  governing-law and term clauses, joined by `\n[...]\n`, so a contract fits a
  4k-token local context. Gold is `expected.tsv` with `_` decoded to spaces;
  `party` is set-valued.

Truncation is lossy and we do not hide it: it is the reason one gold
`effective_date` is unrecoverable from its document (PAPER §5a), and that case
is reported as a limitation rather than dropped.

### The upstream escaping quirk

`dev-0/in.tsv.xz` column 5 stores newlines as the two characters `\` + `n`
(204 of them in document 0). An early version of our converter passed them
through, so the model saw ~70 fake `\n` tokens per contract and words glued
across line breaks. Fixed; the fix is *verifiable at source* — the check script
re-downloads `in.tsv.xz` and re-derives from it. Consequence documented in
PAPER §3 (data statement) and BUILDLOG 36.

The order of operations matters and was itself a bug: unescaping must happen
**before** truncation, or the fake characters consume the 3000-character head
budget and the window lands in a different place. Caught by
`verify_datasets.py` reporting the shipped file was not byte-identical to
converter output; datasets regenerated from upstream and all cells re-run
(BUILDLOG 39).

## Checksums of the shipped files

`sha256`, first 16 hex digits (`python3 -m examples.verify_datasets` recomputes
and compares these against a fresh derivation from upstream):

| file | sha256 (short) | records |
|---|---|---|
| `datasets/kleister_nda.jsonl` | `75bd369e7a8e9604` | 83 |
| `datasets/kleister_nda_party.jsonl` | `4df25323ec8036a0` | 83 |
| `datasets/sroie_50.jsonl` | `6f7c3fd230d9bc96` | 50 |
| upstream `dev-0/expected.tsv` | `2ac328d80ad15688` | 83 |

Last verification run against upstream:

```
Kleister-NDA (applicaai/kleister-nda, split dev-0)
  [OK] kleister_nda_party.jsonl: 83 records, 83/83 gold records match upstream
  [OK] kleister_nda.jsonl:       83 records, 83/83 gold records match upstream
  [OK] kleister_nda_party.jsonl: byte-identical to converter output
  [OK] kleister_nda.jsonl:       byte-identical to converter output
SROIE (ICDAR 2019 Task 3, mirror zzzDavid/ICDAR-2019-SROIE)
  [OK] 6 receipts checked against upstream: 6/6 gold match, 6/6 document text match
```

(The SROIE arm checks `--limit` receipts, two small fetches each; the default
is all 50.)

## The synthetic corpus, and where it is allowed to appear

`fieldguard/data.py` generates seeded synthetic invoices. They exist for two
things only:

1. **Tests** — `MockBackend` needs a corpus with exactly known corruption so
   detector precision/recall are assertable.
2. **`examples/demo.py`** — an offline smoke test that runs with no LLM.

Their numbers are **not results** and are labelled as such wherever they appear
(README "Smoke test, NOT a result"; the demo's 1.000 is true by construction
because the mock backend is a perfect reader and we inject the corruptions).
No table in PAPER.md uses them.

## Metric → dataset map

| metric | dataset backing it |
|---|---|
| constrained / final accuracy, doc-bootstrap CIs | SROIE 50, Kleister-NDA dev-0 (3- and 4-field) |
| corruption rate, flag precision/recall (macro + micro) | same |
| LLM calls vs verify-everything | same |
| ungrounded rate, grounding detection precision | same |
| grounding repair effect (fixed / broken / gold-not-in-doc) | Kleister-NDA dev-0 |
| risk–coverage AURC (combined vs flag / support / random) | all six cells above |
| threshold sweeps | Kleister-NDA dev-0 (n=40 prefix), SROIE 15 |
| everything in `examples/demo.py` | synthetic — **not reported as a result** |

## Citations

- Huang, Z., Chen, K., He, J., Bai, X., Karatzas, D., Lu, S., Jawahar, C. V.
  *ICDAR 2019 Robust Reading Challenge on Scanned Receipts OCR and Information
  Extraction.* ICDAR 2019.
- Stanisławek, T., Graliński, F., Wróblewska, A., Lipiński, D., Kaliska, A.,
  Rosalska, P., Topolski, B., Biecek, P. *Kleister: Key Information Extraction
  Datasets Involving Long Documents with Complex Layouts.* arXiv:2105.05796
  (2021).
