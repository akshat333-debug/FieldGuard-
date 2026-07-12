"""Convert SROIE receipts (box OCR lines + key JSON) to the adapter JSONL shape.

SROIE = ICDAR 2019 Scanned Receipts OCR & IE task: real Malaysian receipts,
gold fields company/date/address/total. Mirror layout (zzzDavid/ICDAR-2019-SROIE):
    key/NNN.json   {"company":..., "date":..., "address":..., "total":...}
    box/NNN.csv    x1,y1,x2,y2,x3,y3,x4,y4,text   (one OCR line per row)

Run:  python3 -m examples.convert_sroie --src /path/to/sroie --out datasets/sroie.jsonl
"""
from __future__ import annotations

import argparse
import json
import pathlib


def box_to_text(csv_path: pathlib.Path) -> str:
    lines = []
    for row in csv_path.read_text(errors="replace").splitlines():
        if not row.strip():
            continue
        parts = row.split(",", 8)  # text itself may contain commas
        if len(parts) == 9:
            lines.append(parts[8])
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True, help="dir containing key/ and box/")
    ap.add_argument("--out", default="datasets/sroie.jsonl")
    args = ap.parse_args()

    src = pathlib.Path(args.src)
    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    records = []
    for key_file in sorted((src / "key").glob("*.json")):
        box_file = src / "box" / (key_file.stem + ".csv")
        if not box_file.exists():
            continue
        gold = json.loads(key_file.read_text())
        doc = box_to_text(box_file)
        if not doc or not all(k in gold for k in ("company", "date", "address", "total")):
            continue
        records.append({"document": doc, "gold": gold})

    with out.open("w") as f:
        for rec in records:
            f.write(json.dumps(rec) + "\n")
    print(f"{len(records)} receipts -> {out}")


if __name__ == "__main__":
    main()
