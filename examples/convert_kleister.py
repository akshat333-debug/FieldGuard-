"""Convert Kleister-NDA (contracts) to the adapter JSONL shape.

Source: applicaai/kleister-nda — in.tsv (col 5 = text_best), expected.tsv
(`key=value` pairs, underscores encode spaces). Single-valued fields only
(effective_date, jurisdiction, term); multi-valued `party` is out of scope for
a flat schema. Docs are long (median ~16k chars): keep head + tail, where the
effective date/parties open the contract and the governing-law clause tends to
sit near the end.

Run:  python3 -m examples.convert_kleister --src /path/to/kleister
      --out datasets/kleister_nda.jsonl
"""
from __future__ import annotations

import argparse
import csv
import json
import pathlib
import sys

FIELDS = ("effective_date", "jurisdiction", "term")
HEAD, TAIL = 3000, 1500
# clauses holding jurisdiction/term sit mid-document; pull a window around them
CLAUSE_KEYWORDS = ("governed by", "governing law", "laws of the",
                   "term of this agreement", "shall remain in effect",
                   "shall terminate", "period of")
WINDOW = 700


def clause_windows(text: str) -> str:
    low = text.casefold()
    spans: list[tuple[int, int]] = []
    for kw in CLAUSE_KEYWORDS:
        i = low.find(kw)
        if i >= 0:
            spans.append((max(0, i - WINDOW // 2), i + WINDOW))
    spans.sort()
    merged: list[list[int]] = []
    for a, b in spans:
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    return "\n[...]\n".join(text[a:b] for a, b in merged)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True, help="dir with in.tsv + expected.tsv")
    ap.add_argument("--out", default="datasets/kleister_nda.jsonl")
    args = ap.parse_args()

    csv.field_size_limit(sys.maxsize)
    src = pathlib.Path(args.src)
    docs = list(csv.reader((src / "in.tsv").open(), delimiter="\t"))
    expected = (src / "expected.tsv").read_text().splitlines()

    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with out.open("w") as f:
        for row, exp in zip(docs, expected):
            gold = {k: v.replace("_", " ")
                    for kv in exp.split() if "=" in kv
                    for k, v in [kv.split("=", 1)]
                    if k in FIELDS}
            # absent fields are legitimate (schema marks them optional):
            # gold "" means "the document does not state it"
            gold = {k: gold.get(k, "") for k in FIELDS}
            # party is multi-valued: every party= entry, as a list
            gold["party"] = [kv.split("=", 1)[1].replace("_", " ")
                             for kv in exp.split() if kv.startswith("party=")]
            text = row[5]
            if len(text) > HEAD + TAIL:
                mid = clause_windows(text[HEAD:len(text) - TAIL])
                text = "\n[...]\n".join(p for p in
                                        (text[:HEAD], mid, text[-TAIL:]) if p)
            f.write(json.dumps({"document": text, "gold": gold}) + "\n")
            n += 1
    print(f"{n} contracts -> {out}")


if __name__ == "__main__":
    main()
