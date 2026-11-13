"""Shows how the upload reads the three date columns of an Excel file, row by row: what is stored in the cell, its format, what pandas hands to the
validation, and whether the date is accepted. Use it when a date is refused and you do not see why. Changes nothing, reads one file.

    docker compose cp my_file.xlsx backend:/tmp/my_file.xlsx
    docker compose exec backend python scripts/check_dates.py /tmp/my_file.xlsx
"""
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
from openpyxl import load_workbook

from app.services.date_rules import read_date
from app.services.template_generator import COLUMNS

DATE_FIELDS = ("disbursement_date", "maturity_date", "collateral_pledged_date")
HEADER_ROW = 9


def main(path):
    data = Path(path).read_bytes()
    ws = load_workbook(io.BytesIO(data))["Loan_Collateral_Data"]
    raw = pd.read_excel(io.BytesIO(data), sheet_name="Loan_Collateral_Data", header=None)
    labels = dict(COLUMNS)
    print(f"pandas {pd.__version__}")
    for field in DATE_FIELDS:
        col = next(c for c in range(1, ws.max_column + 1) if ws.cell(row=HEADER_ROW, column=c).value == labels[field])
        print(f"\n{field}  (column {ws.cell(row=HEADER_ROW, column=col).column_letter})")
        shown = 0
        for r in range(HEADER_ROW + 1, ws.max_row + 1):
            cell = ws.cell(row=r, column=col)
            if cell.value is None:
                continue
            seen = raw.iloc[r - 1, col - 1]
            value, status = read_date(seen)
            print(f"  row {r}: cell={cell.value!r} ({cell.data_type}, format {cell.number_format!r}) -> pandas {seen!r} ({type(seen).__name__}) -> {status}"
                  + (f" {value}" if value else ""))
            shown += 1
            if shown >= 10:
                break
        if shown == 0:
            print("  (no dates in this column)")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("Usage: python scripts/check_dates.py <file.xlsx>")
    main(sys.argv[1])
