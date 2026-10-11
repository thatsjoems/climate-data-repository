"""
Lists the ward names that the repository's geography list and the NBS 2022 ward boundaries spell differently, with the closest NBS spelling
as a SUGGESTION (never applied automatically). Standard library only:

    python backend/scripts/name_differences.py            # prints the table
    python backend/scripts/name_differences.py --csv docs/WARD_NAME_DIFFERENCES.csv

A name counts as the same when, ignoring capitals, spaces and punctuation, the full name, the name without its bracket, or the text inside the
bracket matches. Matching is done inside one region and district.
"""
import argparse
import csv
import difflib
import gzip
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "app" / "data"


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def keys(name: str) -> set[str]:
    ks = {norm(name)}
    base = re.sub(r"\(.*?\)", "", name)
    if norm(base):
        ks.add(norm(base))
    ks |= {norm(m) for m in re.findall(r"\((.*?)\)", name) if norm(m)}
    return ks


def differences():
    geography = json.loads((DATA / "tanzania_geography.json").read_text(encoding="utf-8"))
    wards = json.loads(gzip.open(DATA / "tanzania_ward_boundaries.json.gz").read())["wards"]
    nbs = defaultdict(list)
    for w in wards:
        nbs[(norm(w["r"]), norm(w["d"]))].append((w["r"], w["d"], w["w"].strip()))
    rows = []
    claimed = set()
    for region, districts in geography.items():
        for district, ward_dict in districts.items():
            theirs = nbs.get((norm(region), norm(district)), [])
            their_keys = [(w, keys(w[2])) for w in theirs]
            our_keys = [(w.strip(), keys(w)) for w in ward_dict]
            for ours, ok in our_keys:
                if any(ok & tk for _, tk in their_keys):
                    continue
                pool = [t for t, tk in their_keys if not any(tk & k2 for _, k2 in our_keys)]
                best = difflib.get_close_matches(ours, [t[2] for t in pool], n=1, cutoff=0.6)
                if best:
                    claimed.add((region, district, best[0]))
                rows.append([region.strip(), district.strip(), "only in the repository's list", ours, best[0] if best else "", f"{difflib.SequenceMatcher(None, ours.lower(), best[0].lower()).ratio():.2f}" if best else ""])
            for t, tk in their_keys:
                if any(tk & ok for _, ok in our_keys):
                    continue
                if (region, district, t[2]) in claimed:
                    continue
                rows.append([t[0], t[1], "only in the NBS file", "", t[2], ""])
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv")
    args = ap.parse_args()
    rows = differences()
    head = ["region", "district", "where", "repository_name", "nbs_name_or_suggestion", "similarity"]
    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(head)
            w.writerows(rows)
        print(f"{len(rows)} rows written to {args.csv}")
    else:
        w = csv.writer(sys.stdout)
        w.writerow(head)
        w.writerows(rows)


if __name__ == "__main__":
    main()
