#!/usr/bin/env python3
"""
Writes a test .xlsx that looks like a real bank file: every loan has a region, district and ward and a loan coordinate AND a collateral coordinate that
really lie inside that ward (taken from the boundary data of the application), so a correct file is checked as correct. Nothing else is written or stored.

    docker compose run --rm --no-deps -v "${PWD}\\backend:/app" -v "$HOME\\Downloads:/out" backend python scripts/make_big_file.py /out/loans_100000_coords.xlsx --rows 100000

Then time and profile the check of it (backend/scripts/bench_excel_read.py ... --profile). The older loans_100000.xlsx has no coordinates, which is the expensive part
of a check (docs/LOAD_TESTING.md measured 126 s of checking for such a file), so it does not show what a real bank file costs.
"""
import argparse
import datetime as dt
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from openpyxl import Workbook                                   # noqa: E402

from app.services import boundary_service                      # noqa: E402
from app.services.template_generator import COLUMNS            # noqa: E402

SHEET = "Loan_Collateral_Data"


def interior_point(ward, rnd, tries=300):
    """A (lat, lon) that is inside the ward, or None. Wards are tiny next to their bounding box only rarely, so a few random tries nearly always find one."""
    scale = boundary_service._load().scale
    x0, y0, x1, y1 = ward.bbox
    for _ in range(tries):
        px, py = rnd.uniform(x0, x1), rnd.uniform(y0, y1)
        if ward.contains(px, py):
            return round(py / scale, 6), round(px / scale, 6)
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("output")
    ap.add_argument("--rows", type=int, default=100000)
    ap.add_argument("--wards", type=int, default=1500, help="how many different wards to draw the places from")
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    boundaries = boundary_service._load()
    if boundaries is None:
        print("The boundary data is not in this image, so a file with real coordinates cannot be made.")
        return 1
    rnd = random.Random(args.seed)
    started = time.perf_counter()
    pool = []
    for ward in rnd.sample(boundaries.wards, min(args.wards, len(boundaries.wards))):
        point = interior_point(ward, rnd)
        if point:
            pool.append((ward.place, point))
    if not pool:
        print("No ward with an inside point was found.")
        return 1
    print(f"{len(pool)} wards with a point inside them, found in {time.perf_counter() - started:.1f} s")

    labels = dict(COLUMNS)
    fields = [f for f, _ in COLUMNS]
    wb = Workbook(write_only=True)
    ws = wb.create_sheet(SHEET)
    ws.append([labels[f] for f in fields])
    base = dt.datetime(2024, 1, 15)
    for i in range(args.rows):
        place, (lat, lon) = rnd.choice(pool)
        c_place, (c_lat, c_lon) = (place, (lat, lon)) if rnd.random() < 0.6 else rnd.choice(pool)
        loan = rnd.randint(1, 500) * 1_000_000
        row = {
            "customer_id": f"CUST-BIG-{i:07d}", "loan_id": f"LN-BIG-{i:07d}",
            "disbursement_date": base + dt.timedelta(days=rnd.randint(0, 700)), "maturity_date": base + dt.timedelta(days=rnd.randint(800, 2500)),
            "loan_amount_tzs": loan, "outstanding_principal_tzs": int(loan * rnd.uniform(0.2, 1.0)), "annual_interest_rate": round(rnd.uniform(5, 25), 2),
            "region": place.region, "district": place.district, "ward": place.ward, "loan_latitude": lat, "loan_longitude": lon,
            "collateral_type": "Residential mortgage", "collateral_pledged_date": base + dt.timedelta(days=rnd.randint(0, 700)),
            "collateral_value_tzs": int(loan * rnd.uniform(1.0, 1.6)),
            "collateral_region": c_place.region, "collateral_district": c_place.district, "collateral_ward": c_place.ward,
            "collateral_latitude": c_lat, "collateral_longitude": c_lon,
        }
        ws.append([row.get(f) for f in fields])
    wb.save(args.output)
    size = Path(args.output).stat().st_size / 1_048_576
    print(f"Wrote {args.rows:,} loans to {args.output} ({size:.1f} MB) in {time.perf_counter() - started:.0f} s")

    # A short check of the start of the file, so a file whose places the application does not recognise is noticed here and not after a long upload.
    from app.services.validation_service import validate_excel_file
    sample = Workbook(write_only=True)
    ws2 = sample.create_sheet(SHEET)
    ws2.append([labels[f] for f in fields])
    import openpyxl
    reader = openpyxl.load_workbook(args.output, read_only=True)
    for n, line in enumerate(reader[SHEET].iter_rows(values_only=True)):
        if 0 < n <= 2000:
            ws2.append(list(line))
        if n > 2000:
            break
    import io
    buffer = io.BytesIO()
    sample.save(buffer)
    records, issues = validate_excel_file(buffer.getvalue(), "sample.xlsx", form_reporting_period="2026-Q1")
    errors = [i for i in issues if i.severity == "ERROR"]
    print(f"A check of the first {len(records):,} loans: {len(errors)} errors, {len(issues) - len(errors)} warnings")
    for issue in issues[:5]:
        print("  ", issue.severity, issue.row_number, issue.column_name, issue.description[:150])
    return 0 if len(errors) <= len(records) * 0.01 else 1


if __name__ == "__main__":
    sys.exit(main())
