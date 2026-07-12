"""Accuracy vs verification-cost figure: three models on SROIE-50.

Reads results/sroie_50_desc_*_n50_t0.5.json, emits docs/tradeoff_sroie.svg
(stdlib only). Run:  python3 -m examples.figure
"""
from __future__ import annotations

import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent

# palette: categorical slots 1-3 (CVD-validated order), chrome inks
BLUE, AQUA, YELLOW = "#2a78d6", "#1baf7a", "#eda100"
INK, INK2, MUTED = "#0b0b0b", "#52514e", "#898781"
GRID, AXIS, SURFACE = "#e1e0d9", "#c3c2b7", "#fcfcfb"

W, H = 720, 430
ML, MR, MT, MB = 64, 24, 56, 48
PW, PH = W - ML - MR, H - MT - MB
X_MAX, Y_MAX = 330, 1.0

MODELS = (  # (results tag, display name, color, label side: +1 right / -1 left)
    ("qwen2.5_3b", "qwen2.5:3b", BLUE, +1),
    ("qwen2.5_1.5b", "qwen2.5:1.5b", AQUA, -1),
    ("tinyllama_latest", "tinyllama-1.1B", YELLOW, -1),
)


def sx(calls: float) -> float:
    return ML + calls / X_MAX * PW


def sy(acc: float) -> float:
    return MT + (1 - acc / Y_MAX) * PH


def main() -> None:
    s = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
         f'viewBox="0 0 {W} {H}" font-family="system-ui, sans-serif">',
         f'<rect width="{W}" height="{H}" fill="{SURFACE}"/>',
         f'<text x="{ML}" y="24" font-size="15" font-weight="600" fill="{INK}">'
         f'Accuracy vs verification cost — SROIE receipts (50 docs / 200 fields)</text>',
         f'<text x="{ML}" y="42" font-size="12" fill="{INK2}">'
         f'One point per model at the default threshold. Verification spend adapts '
         f'to model quality.</text>']

    for acc in (0.0, 0.25, 0.5, 0.75, 1.0):
        y = sy(acc)
        s.append(f'<line x1="{ML}" y1="{y:.1f}" x2="{ML+PW}" y2="{y:.1f}" '
                 f'stroke="{GRID}" stroke-width="1"/>')
        s.append(f'<text x="{ML-8}" y="{y+4:.1f}" font-size="11" fill="{MUTED}" '
                 f'text-anchor="end">{acc:.2f}</text>')
    for calls in (0, 50, 100, 150, 200, 250, 300):
        s.append(f'<text x="{sx(calls):.1f}" y="{MT+PH+18}" font-size="11" '
                 f'fill="{MUTED}" text-anchor="middle">{calls}</text>')
    s.append(f'<line x1="{ML}" y1="{MT+PH}" x2="{ML+PW}" y2="{MT+PH}" '
             f'stroke="{AXIS}" stroke-width="1"/>')
    s.append(f'<text x="{ML+PW/2}" y="{H-10}" font-size="12" fill="{INK2}" '
             f'text-anchor="middle">LLM calls (50 docs)</text>')
    s.append(f'<text x="16" y="{MT+PH/2}" font-size="12" fill="{INK2}" '
             f'text-anchor="middle" transform="rotate(-90 16 {MT+PH/2})">final accuracy</text>')

    x300 = sx(300)
    s.append(f'<line x1="{x300:.1f}" y1="{MT}" x2="{x300:.1f}" y2="{MT+PH}" '
             f'stroke="{AXIS}" stroke-width="1" stroke-dasharray="4 4"/>')
    s.append(f'<text x="{x300-6:.1f}" y="{MT+12}" font-size="11" fill="{MUTED}" '
             f'text-anchor="end">verify-everything cost</text>')

    for tag, name, color, side in MODELS:
        rep = json.loads((ROOT / "results" /
                          f"sroie_50_desc_{tag}_n50_t0.5.json").read_text())["report"]
        calls, acc, full = rep["llm_calls"], rep["final_acc"], rep["full_verify_calls"]
        x, y = sx(calls), sy(acc)
        saved = 1 - calls / full
        s.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" fill="{color}" '
                 f'stroke="{SURFACE}" stroke-width="2"/>')
        anchor = "start" if side > 0 else "end"
        dx = 12 * side
        s.append(f'<text x="{x+dx:.1f}" y="{y-12:.1f}" font-size="12" '
                 f'font-weight="600" fill="{INK}" text-anchor="{anchor}">{name}</text>')
        s.append(f'<text x="{x+dx:.1f}" y="{y+3:.1f}" font-size="11" fill="{INK2}" '
                 f'text-anchor="{anchor}">acc {acc:.3f} · {calls} calls '
                 f'({saved:.0%} saved)</text>')

    lx = ML + 8
    for i, (_, name, color, _) in enumerate(MODELS):
        y = MT + 10 + i * 18
        s.append(f'<circle cx="{lx}" cy="{y}" r="5" fill="{color}"/>')
        s.append(f'<text x="{lx+12}" y="{y+4}" font-size="12" fill="{INK2}">{name}</text>')

    s.append("</svg>")
    out = ROOT / "docs" / "tradeoff_sroie.svg"
    out.write_text("\n".join(s))
    print(f"figure -> {out}")


if __name__ == "__main__":
    main()
