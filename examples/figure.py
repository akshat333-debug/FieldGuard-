"""Accuracy vs verification-cost figure from SROIE sweep results.

Reads results/sweep_sroie_15_*.json, emits docs/tradeoff_sroie.svg (stdlib only).

Run:  python3 -m examples.figure
"""
from __future__ import annotations

import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent

# palette: categorical slots 1-2 (validated), chrome inks
BLUE, AQUA = "#2a78d6", "#1baf7a"
INK, INK2, MUTED = "#0b0b0b", "#52514e", "#898781"
GRID, AXIS, SURFACE = "#e1e0d9", "#c3c2b7", "#fcfcfb"

W, H = 720, 430
ML, MR, MT, MB = 64, 24, 56, 48  # margins
PW, PH = W - ML - MR, H - MT - MB

X_MAX, Y_MAX = 100, 1.0


def sx(calls: float) -> float:
    return ML + calls / X_MAX * PW


def sy(acc: float) -> float:
    return MT + (1 - acc / Y_MAX) * PH


def load(model_tag: str) -> list[dict]:
    return json.loads((ROOT / "results" / f"sweep_sroie_15_{model_tag}_n15.json")
                      .read_text())


def dedupe(points: list[dict]) -> list[tuple[float, float, list[float]]]:
    """Group thresholds landing on the same (calls, acc) point."""
    seen: dict[tuple, list[float]] = {}
    for p in points:
        seen.setdefault((p["llm_calls"], round(p["final_acc"], 3)), []).append(
            p["threshold"])
    return [(c, a, ts) for (c, a), ts in seen.items()]


def main() -> None:
    qwen, tiny = load("qwen2.5_3b"), load("tinyllama_latest")
    full_cost = 90

    s = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
         f'viewBox="0 0 {W} {H}" font-family="system-ui, sans-serif">',
         f'<rect width="{W}" height="{H}" fill="{SURFACE}"/>',
         f'<text x="{ML}" y="24" font-size="15" font-weight="600" fill="{INK}">'
         f'Accuracy vs verification cost — SROIE receipts (15 docs / 60 fields)</text>',
         f'<text x="{ML}" y="42" font-size="12" fill="{INK2}">'
         f'Each point: one disagreement threshold. Verification spend adapts to model quality.</text>']

    # gridlines + y axis labels
    for acc in (0.0, 0.25, 0.5, 0.75, 1.0):
        y = sy(acc)
        s.append(f'<line x1="{ML}" y1="{y:.1f}" x2="{ML+PW}" y2="{y:.1f}" '
                 f'stroke="{GRID}" stroke-width="1"/>')
        s.append(f'<text x="{ML-8}" y="{y+4:.1f}" font-size="11" fill="{MUTED}" '
                 f'text-anchor="end">{acc:.2f}</text>')
    # x axis ticks
    for calls in (0, 15, 30, 45, 60, 75, 90):
        x = sx(calls)
        s.append(f'<text x="{x:.1f}" y="{MT+PH+18}" font-size="11" fill="{MUTED}" '
                 f'text-anchor="middle">{calls}</text>')
    # baseline axis
    s.append(f'<line x1="{ML}" y1="{MT+PH}" x2="{ML+PW}" y2="{MT+PH}" '
             f'stroke="{AXIS}" stroke-width="1"/>')
    # axis titles
    s.append(f'<text x="{ML+PW/2}" y="{H-10}" font-size="12" fill="{INK2}" '
             f'text-anchor="middle">LLM calls (15 docs)</text>')
    s.append(f'<text x="16" y="{MT+PH/2}" font-size="12" fill="{INK2}" '
             f'text-anchor="middle" transform="rotate(-90 16 {MT+PH/2})">final accuracy</text>')

    # verify-everything reference line
    x90 = sx(full_cost)
    s.append(f'<line x1="{x90:.1f}" y1="{MT}" x2="{x90:.1f}" y2="{MT+PH}" '
             f'stroke="{AXIS}" stroke-width="1" stroke-dasharray="4 4"/>')
    s.append(f'<text x="{x90-6:.1f}" y="{MT+12}" font-size="11" fill="{MUTED}" '
             f'text-anchor="end">verify-everything cost</text>')

    def point(calls, acc, color):
        s.append(f'<circle cx="{sx(calls):.1f}" cy="{sy(acc):.1f}" r="5" '
                 f'fill="{color}" stroke="{SURFACE}" stroke-width="2"/>')

    def label(calls, acc, text, dx, dy, anchor, weight="400", ink=INK2, size=11):
        s.append(f'<text x="{sx(calls)+dx:.1f}" y="{sy(acc)+dy:.1f}" '
                 f'font-size="{size}" font-weight="{weight}" fill="{ink}" '
                 f'text-anchor="{anchor}">{text}</text>')

    # qwen cluster: t>=0.5 at (35, 0.850), t=0.3 at (38, 0.833) — labels hand-
    # placed on opposite sides to avoid collision
    for calls, acc, ts in dedupe(qwen):
        point(calls, acc, BLUE)
        if len(ts) > 1:
            label(calls, acc, f"t≥0.5 · acc {acc:.3f} · {calls} calls",
                  -12, 4, "end")
        else:
            label(calls, acc, f"t=0.3 · acc {acc:.3f} · {calls} calls",
                  12, 14, "start")
    label(35, 0.850, "qwen2.5:3b", -12, -14, "end", weight="600", ink=INK, size=12)

    # tinyllama: single point pinned at full cost
    for calls, acc, ts in dedupe(tiny):
        point(calls, acc, AQUA)
        label(calls, acc, f"all thresholds · acc {acc:.3f} · {calls} calls",
              -12, -10, "end")
    label(90, 0.067, "tinyllama-1.1B", -12, -26, "end", weight="600", ink=INK,
          size=12)

    # legend (2 series)
    lx = ML + 8
    for i, (color, name) in enumerate(((BLUE, "qwen2.5:3b"), (AQUA, "tinyllama-1.1B"))):
        y = MT + 10 + i * 18
        s.append(f'<circle cx="{lx}" cy="{y}" r="5" fill="{color}"/>')
        s.append(f'<text x="{lx+12}" y="{y+4}" font-size="12" fill="{INK2}">{name}</text>')

    s.append("</svg>")
    out = ROOT / "docs" / "tradeoff_sroie.svg"
    out.write_text("\n".join(s))
    print(f"figure -> {out}")


if __name__ == "__main__":
    main()
