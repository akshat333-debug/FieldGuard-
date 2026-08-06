"""Unified per-field confidence: one number from both signals + the resolution.

Every stage of the pipeline already produces an ordinal reliability cue:

    resolution source   agreement > majority > split-kept   (signal 1 + arbiter)
    grounding support   1.0 .. 0.0                          (signal 2)

This module folds them into a single score in (0, 1] so a downstream consumer
can rank fields by trustworthiness and choose its own review budget — the
selective-prediction use of the system (risk–coverage curves in
``examples/risk_coverage.py``).

The weights are fixed constants, not fitted — there is nothing to train and
nothing to leak. Only the *ranking* is claimed: a field that both paths agreed
on and the source supports outranks a corroborated repair, which outranks an
uncorroborated flag, and grounding degrades each band smoothly. Absolute values
are not calibrated probabilities and are documented as such.
"""
from __future__ import annotations

_SOURCE_WEIGHT = {
    "agreement": 1.0,   # both paths produced it independently
    "majority": 0.7,    # disputed, but the blind arbiter corroborated a path
    "split-kept": 0.3,  # disputed and uncorroborated — kept, flagged for review
}


def confidence(source: str, support: float) -> float:
    """Score in (0, 1]: resolution band, degraded by missing source support."""
    return _SOURCE_WEIGHT[source] * (0.5 + 0.5 * support)
