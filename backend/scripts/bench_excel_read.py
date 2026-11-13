#!/usr/bin/env python3
"""
Times the two ways of reading an .xlsx upload on a real file, and checks that they give the same cells. Changes nothing (no database, no files written).

    docker compose cp loans_100000.xlsx backend:/tmp/loans_100000.xlsx
    docker compose exec backend python scripts/bench_excel_read.py /tmp/loans_100000.xlsx            (the two readers, and a comparison of every cell)
    docker compose exec backend python scripts/bench_excel_read.py /tmp/loans_100000.xlsx --full     (also the whole check of the file with each reader, as an upload does)

Production: the same with `docker compose -f docker-compose.prod.yml --env-file .env.production exec backend ...` (it only reads the copy under /tmp).
Exit code 0 = same cells (and, with --full, the same records and findings); 1 = a difference or a failure: do not switch production to the fast reader.
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd                                         # noqa: E402

from app.core.config import settings                        # noqa: E402
from app.services import excel_reader                       # noqa: E402
from app.services.validation_service import validate_excel_file   # noqa: E402

SHEET = "Loan_Collateral_Data"


def timed(label, function):
    start = time.perf_counter()
    result = function()
    seconds = time.perf_counter() - start
    print(f"  {label:<38} {seconds:8.1f} s")
    return result, seconds


def differences(first: pd.DataFrame, second: pd.DataFrame, limit=10):
    """Cells that differ (a Timestamp and a datetime of the same moment are the same), at most `limit` of them."""
    if first.shape != second.shape:
        return [f"shape {first.shape} against {second.shape}"]
    found = []
    a_rows = first.to_numpy(dtype=object)
    b_rows = second.to_numpy(dtype=object)
    for r in range(a_rows.shape[0]):
        for c in range(a_rows.shape[1]):
            a, b = a_rows[r, c], b_rows[r, c]
            if pd.isna(a) and pd.isna(b):
                continue
            same = (pd.Timestamp(a) == pd.Timestamp(b)) if hasattr(a, "year") and hasattr(b, "year") else (type(a) is type(b) and a == b)
            if not same:
                found.append(f"row {r + 1}, column {c + 1}: {a!r} against {b!r}")
                if len(found) >= limit:
                    return found
    return found


def summary(records, issues):
    return ([sorted((k, str(v)) for k, v in r.items()) for r in records],
            [(i.row_number, i.column_name, i.description, i.severity) for i in issues])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file")
    ap.add_argument("--full", action="store_true", help="also check the whole file with each reader (takes minutes for 100,000 loans)")
    args = ap.parse_args()
    data = Path(args.file).read_bytes()
    print(f"{args.file}: {len(data) / 1_048_576:.1f} MB")

    print("Reading the sheet only:")
    try:
        old, old_s = timed("openpyxl (the old reader)", lambda: excel_reader._read("openpyxl", data, SHEET))
    except Exception as exc:
        print("FAILED with openpyxl:", type(exc).__name__, exc)
        return 1
    try:
        new, new_s = timed("calamine (the fast reader)", lambda: excel_reader._read("calamine", data, SHEET))
    except Exception as exc:
        print("FAILED with calamine:", type(exc).__name__, exc)
        return 1
    print(f"  the fast reader is {old_s / new_s:.1f} times faster" if new_s else "")

    found, _ = timed("comparing every cell", lambda: differences(old, new))
    if found:
        print("DIFFERENT CELLS (the first ones):")
        for line in found:
            print("  ", line)
        print("RESULT: NOT THE SAME. Do not use the fast reader for this kind of file (set EXCEL_READER=openpyxl) and send this output to the developer.")
        return 1
    print(f"  all {old.shape[0] * old.shape[1]:,} cells are the same ({old.shape[0]:,} rows, {old.shape[1]} columns)")

    if args.full:
        print("Checking the whole file, as an upload does:")
        answers = {}
        for setting in ("openpyxl", "calamine"):
            settings.EXCEL_READER = setting
            (records, issues), _ = timed(f"EXCEL_READER={setting}", lambda: validate_excel_file(data, "bench.xlsx"))
            answers[setting] = summary(records, issues)
            print(f"    {len(records):,} records, {len(issues):,} findings")
        if answers["openpyxl"] != answers["calamine"]:
            print("RESULT: THE RECORDS OR FINDINGS DIFFER between the readers. Do not use the fast reader; send this output to the developer.")
            return 1
        print("  the same records and the same findings")
    print("RESULT: the same cells; the fast reader is safe for this file.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
