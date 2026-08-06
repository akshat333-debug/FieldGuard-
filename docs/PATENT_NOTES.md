# Patent notes — inventive concept, claim skeleton, prior-art register

**Status: working notes for a patent attorney, not legal advice.** Everything
here comes from literature searches. A filing decision needs a professional
freedom-to-operate (FTO) search of patent databases — that work has NOT been
done and cannot be replaced by anything in this repo.

## 1. The inventive concept, stated the way an examiner needs it

Not "detecting hallucinations" (crowded) and not "per-field confidence for
extraction" (PromptPort and US12032919B1 are precedent). The candidate
inventive step is narrower and structural:

> Using the **decoding constraint itself as the manipulated variable** — the
> same model, same document, same temperature, sampled once with schema-forced
> decoding and once without — and treating **per-field divergence between the
> two decodes as a targeting signal** that routes *only* divergent fields to a
> verification step, the verifier being **blind** to the divergent candidate
> values.

Supporting dependent features, each individually measured in this repo:

1. **Type-aware canonical comparison** before divergence scoring (dates,
   numbers, corporate suffixes, spelled-out numbers, set-valued fields), so
   formatting differences do not consume the verification budget.
2. **Blind single-field arbiter** — the re-verification query names the field
   but never shows the disputed values (candidate-aware judging measurably
   manufactured false majorities; BUILDLOG 19).
3. **Split-kept resolution** — an uncorroborated divergence keeps the
   production (constrained) value and lowers confidence rather than accepting
   the arbiter answer (arbiter-wins measurably damaged accuracy; BUILDLOG 17).
4. **Structural absence** — optional fields expressed only through the JSON
   required-list, never as an "answer NONE" instruction shared by both decodes
   (a shared absence instruction correlates the two decodes and destroys the
   divergence signal; BUILDLOG 21).
5. **Second, orthogonal signal**: lexical source-support scoring of the kept
   value against the input document, with a **gold-free runtime gate**
   (ungrounded rate) that switches a repair rule on only for extractors whose
   ungrounded rate indicates fabrication (~15% vs ~4%; capability-adaptive
   behavior, measured both ways).
6. **Unified per-field confidence** = resolution band × source support, used
   for selective prediction (risk–coverage measured in
   `examples/risk_coverage.py`).
7. **Cost adaptivity as an emergent property** — verification spend tracks
   extractor quality with no tuned knob (61% → 56% → 0% saved as the extractor
   degrades), because the divergence rate is itself the budget.

The strongest claim shape is independent claim = the dual-decode differential
targeting + blind selective verification loop (the combination), with 1–7 as
dependents. The combination is what the prior art below does not show.

## 2. Prior-art register (found by us; an attorney must extend this)

| Reference | What it covers | Why the concept above survives it (our reading) |
|---|---|---|
| PromptPort, arXiv:2601.06151 | per-field confidence, field-level override, safe-override policy | confidence comes from a *trained verifier model*; no constraint manipulation, no blind arbiter, no gold-free repair gate |
| US12032919B1 | post-calibration of LLM confidence for document extraction | calibrates scores an extractor already emits; does not generate a second unconstrained decode as the signal |
| US12353469B1 | verification & citation of LM outputs | verifies against sources (adjacent to our signal 2); not field-differential between two decodes of one model |
| Self-consistency (Wang et al., 2022) | majority over k samples, same prompt | same prompt each sample — the constraint is never the manipulated variable; no selective routing, no blind arbiter |
| Two-stage / re-ask pipelines | re-process everything | no targeting; cost is flat, not divergence-driven |
| JSONSchemaBench / structured-output benchmarks | score schema compliance | measurement, not mechanism |

Honest overlaps we will not claim: per-field confidence as such, field-level
override as such, safe/conservative override as such (all PromptPort);
verification against sources as such (US12353469B1).

## 3. What weakens a filing (say this to the attorney up front)

- Public disclosure: this repo is public on GitHub. In first-to-file systems
  with no grace period (most of Europe), our own publication is prior art
  against us the moment it went public. India has no general grace period
  either. If filing matters, file a **provisional before the paper preprint**,
  and get advice on what the GitHub history already forecloses.
- The core mechanism is a prompt-engineering-adjacent method; expect
  patentable-subject-matter pushback (Alice/s.3(k) style). The concrete,
  measured cost-routing effect (7) is the best technical-effect anchor.
- Inventorship: this must be cleared with the institution; prior filing
  IN202641051569 A1 has different co-inventors and different subject matter —
  keep the two strictly separate in all paperwork.

## 4. Publication path (the complement)

The same 1–7 list is the paper's contribution list. Venue guidance in
PAPER.md §venue: workshop track (ACL/EMNLP/NAACL workshops, ICON,
LREC-COLING) given 2 domains × 3 small models. Provisional-then-preprint if
both routes are wanted.
