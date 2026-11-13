# How an uploaded Excel file is read

Reading the sheet is the biggest single step of checking a large upload (about 126 of the 204 seconds for 100,000 loans, `docs/LOAD_TESTING.md`).
Since November 2026 the sheet of an `.xlsx` file is read with **calamine** (a reader written in Rust, used through pandas) instead of openpyxl, which is much faster.
The template, the columns, the date rules and everything the institution sees are unchanged: only the part that fetches the cells is different.

## What keeps it safe

| Protection | How |
|---|---|
| Same cells | `tests/test_excel_reader.py` reads the same workbooks with both readers and compares every cell (numbers, decimals, dates, text dates, blanks, yes/no, a serial number in a General cell) and the whole check of a file (records and findings). |
| Fallback | If calamine is missing or fails, the file is read again with openpyxl, exactly as before. Nobody sees the difference. |
| Way back, no rebuild | Put `EXCEL_READER=openpyxl` in `.env.production` and run `docker compose -f docker-compose.prod.yml --env-file .env.production up -d backend`. |
| Only real `.xlsx` | A file that is not a ZIP package (an old `.xls`, for example) keeps the old reader. |
| Dates | Unchanged. `app/services/date_rules.py` is applied to whatever the reader returns: a real date cell is accepted, a number is refused. |

`EXCEL_READER` values: `auto` (default: calamine, then openpyxl), `openpyxl` (the old reader only), `calamine` (the fast reader only, for tests and measurements).

## Measuring it on a real file

```powershell
docker compose cp loans_100000.xlsx backend:/tmp/loans_100000.xlsx
docker compose exec backend python scripts/bench_excel_read.py /tmp/loans_100000.xlsx           # both readers, every cell compared
docker compose exec backend python scripts/bench_excel_read.py /tmp/loans_100000.xlsx --full    # and the whole check, as an upload does
```
`RESULT: the same cells; the fast reader is safe for this file.` means it can be used. Any other result: set `EXCEL_READER=openpyxl` and send the output to the developer.

## Dependency

`python-calamine==0.3.2` (MIT licence, a Rust library with ready-made wheels; no compiler needed), pinned in `backend/requirements.txt`; see `docs/DEPENDENCY_SECURITY.md`.

## What it does not change

It makes one upload faster. It does not change how many uploads are handled at the same time: they still share one process (see `docs/LOAD_TESTING.md`). Checking in the background, with progress, is the next step if the Bank expects many large files at once.
