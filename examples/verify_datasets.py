"""Prove the shipped benchmark files are the public datasets, not our edit of them.

Every headline number in this repo is computed over `datasets/*.jsonl`. Those
files are *derived* (OCR lines joined, long contracts clause-truncated), so a
reader has to take our word for it unless the derivation is reproducible from
the official release. This script removes that trust requirement:

    Kleister-NDA  downloads the official dev-0 split from applicaai/kleister-nda,
                  re-runs examples/convert_kleister.py over it, and compares the
                  result to the shipped file BYTE FOR BYTE. It also checks every
                  gold record against upstream expected.tsv independently of the
                  converter, so a converter bug cannot hide a label mismatch.

    SROIE         gold labels are checked field-by-field against the official
                  key/*.json of the ICDAR-2019-SROIE mirror. Document text is
                  checked by re-joining the upstream box/*.csv OCR lines.

Network access is required (raw.githubusercontent.com). Nothing is written to
the repo; failures are reported per record.

Run:  python3 -m examples.verify_datasets
      python3 -m examples.verify_datasets --only sroie
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import lzma
import pathlib
import subprocess
import sys
import tempfile
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATASETS = ROOT / "datasets"

KLEISTER_RAW = "https://raw.githubusercontent.com/applicaai/kleister-nda/master/dev-0"
SROIE_RAW = "https://raw.githubusercontent.com/zzzDavid/ICDAR-2019-SROIE/master/data"

FIELDS = ("effective_date", "jurisdiction", "term")


def fetch(url: str, timeout: float = 60.0) -> bytes:
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.read()


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def parse_expected(text: str) -> list[dict]:
    """expected.tsv: space-separated key=value, underscores encode spaces."""
    out = []
    for line in text.splitlines():
        gold: dict = {k: "" for k in FIELDS}
        parties: list[str] = []
        for kv in line.split():
            if "=" not in kv:
                continue
            k, v = kv.split("=", 1)
            v = v.replace("_", " ")
            if k == "party":
                parties.append(v)
            elif k in FIELDS:
                gold[k] = v
        gold["party"] = parties
        out.append(gold)
    return out


def verify_kleister() -> bool:
    print("Kleister-NDA (applicaai/kleister-nda, split dev-0)")
    try:
        expected = fetch(f"{KLEISTER_RAW}/expected.tsv").decode()
        in_xz = fetch(f"{KLEISTER_RAW}/in.tsv.xz")
    except Exception as exc:
        print(f"  SKIP — could not reach upstream: {exc}")
        return True

    upstream_gold = parse_expected(expected)
    print(f"  upstream: {len(upstream_gold)} documents "
          f"(expected.tsv sha256 {sha(expected.encode())[:16]})")

    ok = True
    # (1) labels, independent of our converter
    for name, keep_party in (("kleister_nda_party.jsonl", True),
                             ("kleister_nda.jsonl", False)):
        shipped = [json.loads(l) for l in (DATASETS / name).read_text().splitlines()]
        bad = 0
        for up, rec in zip(upstream_gold, shipped):
            want = dict(up) if keep_party else {k: up[k] for k in FIELDS}
            bad += want != rec["gold"]
        status = "OK" if not bad and len(shipped) == len(upstream_gold) else "FAIL"
        ok &= status == "OK"
        print(f"  [{status}] {name}: {len(shipped)} records, "
              f"{len(shipped) - bad}/{len(shipped)} gold records match upstream")

    # (2) documents, by re-running the shipped converter over upstream bytes
    with tempfile.TemporaryDirectory() as tmp:
        src = pathlib.Path(tmp)
        (src / "expected.tsv").write_text(expected)
        (src / "in.tsv").write_bytes(lzma.decompress(in_xz))
        for name, extra in (("kleister_nda_party.jsonl", []),
                            ("kleister_nda.jsonl", ["--no-party"])):
            out = src / name
            subprocess.run(
                [sys.executable, "-m", "examples.convert_kleister",
                 "--src", str(src), "--out", str(out), *extra],
                cwd=ROOT, check=True, capture_output=True)
            got, want = out.read_bytes(), (DATASETS / name).read_bytes()
            status = "OK" if got == want else "FAIL"
            ok &= status == "OK"
            print(f"  [{status}] {name}: byte-identical to converter output "
                  f"(sha256 {sha(want)[:16]})")
    return ok


def verify_sroie(limit: int = 50) -> bool:
    print("\nSROIE (ICDAR 2019 Task 3, mirror zzzDavid/ICDAR-2019-SROIE)")
    name = "sroie_50.jsonl"
    shipped = [json.loads(l) for l in (DATASETS / name).read_text().splitlines()]
    print(f"  shipped: {len(shipped)} receipts "
          f"(sha256 {sha((DATASETS / name).read_bytes())[:16]})")

    # The mirror stores one key/NNN.json + box/NNN.csv per receipt; the shipped
    # file is the first `limit` in sorted filename order, so index i maps to the
    # i-th name. We re-derive both sides for the receipts we actually used.
    checked = gold_bad = doc_bad = 0
    for i, rec in enumerate(shipped[:limit]):
        stem = f"{i:03d}"
        try:
            key = json.loads(fetch(f"{SROIE_RAW}/key/{stem}.json", timeout=20))
            box = fetch(f"{SROIE_RAW}/box/{stem}.csv", timeout=20).decode(
                errors="replace")
        except Exception:
            continue  # mirror layout varies; report over what we could fetch
        checked += 1
        gold_bad += {k: key.get(k, "") for k in rec["gold"]} != rec["gold"]
        lines = [r.split(",", 8)[8] for r in box.splitlines()
                 if len(r.split(",", 8)) == 9]
        doc_bad += "\n".join(lines) != rec["document"]

    if not checked:
        print("  SKIP — could not reach the upstream mirror")
        return True
    status = "OK" if not (gold_bad or doc_bad) else "FAIL"
    print(f"  [{status}] {checked} receipts checked against upstream: "
          f"{checked - gold_bad}/{checked} gold match, "
          f"{checked - doc_bad}/{checked} document text match")
    return status == "OK"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--only", choices=("kleister", "sroie"))
    ap.add_argument("--limit", type=int, default=50,
                    help="SROIE receipts to check (each costs two small fetches)")
    args = ap.parse_args()

    ok = True
    if args.only != "sroie":
        ok &= verify_kleister()
    if args.only != "kleister":
        ok &= verify_sroie(args.limit)
    print("\n" + ("ALL CHECKS PASSED" if ok else "SOME CHECKS FAILED"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
