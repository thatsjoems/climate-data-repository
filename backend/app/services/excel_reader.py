"""
Reads the sheet of an uploaded .xlsx file into a table of plain cells (no header row is assumed: the caller finds the header itself).

Why this exists. Reading the sheet with openpyxl is the largest single step of checking a big upload (docs/LOAD_TESTING.md: 126 s of the 204 s for a file of
100,000 loans). `calamine` (a reader written in Rust, supported by pandas as engine="calamine") reads the same file much faster.

How it is kept safe:
* Only a real .xlsx (a ZIP package) is sent to calamine. Anything else keeps the reader it always had.
* If calamine is not installed, or fails for any reason, the file is read again with openpyxl, exactly as before. The person never sees the difference.
* EXCEL_READER decides: "auto" (calamine, then openpyxl: the default), "openpyxl" (the old reader only: the way back, set it in .env.production
  and restart the backend, no rebuild), or "calamine" (calamine only, for tests and measurements).
* Both readers give the same cells: pandas converts a whole number to int, a date-formatted cell to a Timestamp and an empty cell to NaN in both
  (tests/test_excel_reader.py compares them cell by cell; backend/scripts/bench_excel_read.py does the same on a real file and times each).
The date rules (app/services/date_rules.py) are applied afterwards, to whatever this module returns, and are unchanged.
"""
import io
import logging

import pandas as pd

from app.core.config import settings

log = logging.getLogger("cdr.excel")

_XLSX_SIGNATURE = b"PK"          # an .xlsx file is a ZIP package; an old .xls or anything else is not


def engines_for(file_bytes: bytes) -> list[str]:
    """The readers to try, in order, for this file and the current EXCEL_READER setting."""
    choice = str(getattr(settings, "EXCEL_READER", "auto") or "auto").strip().lower()
    if choice == "openpyxl" or not file_bytes.startswith(_XLSX_SIGNATURE):
        return ["openpyxl"]
    if choice == "calamine":
        return ["calamine"]
    return ["calamine", "openpyxl"]


def _read(engine: str, file_bytes: bytes, sheet_name):
    kwargs = {"header": None, "engine": engine}
    if sheet_name is not None:
        kwargs["sheet_name"] = sheet_name
    return pd.read_excel(io.BytesIO(file_bytes), **kwargs)


def read_excel_grid(file_bytes: bytes, sheet_name=None) -> "pd.DataFrame":
    """The sheet (the one called sheet_name, or the first when it is None) as a table without a header. Raises what the last reader raised."""
    last_error = None
    engines = engines_for(file_bytes)
    for position, engine in enumerate(engines):
        try:
            return _read(engine, file_bytes, sheet_name)
        except Exception as exc:                                  # a missing sheet or a damaged file also lands here: the next reader gets its turn
            last_error = exc
            if position + 1 < len(engines):
                log.warning("reading with %s failed (%s: %s); trying %s", engine, type(exc).__name__, str(exc)[:200], engines[position + 1])
    raise last_error
