# Dates in an uploaded file

A loan file has three date columns: **disbursement date**, **maturity date** and **collateral pledged date**. They are optional, but a date that is present must be one the system can read with certainty. This page is for the institutions that prepare the files and for the Bank's analysts who explain a finding.

## What is accepted

| How the date is written | Example | Result |
|---|---|---|
| A real Excel date cell | (formatted as a date) | Accepted. **This is the safest way.** |
| Year first | `2026-03-15`, `2026/03/15`, `2026.03.15`, `20260315` | Accepted (any time of day is ignored) |
| Day, month, year, when only one reading is possible | `25/03/2026`, `25-03-2026` (the 25th cannot be a month) | Accepted as 25 March 2026 |
| Month, day, year, when only one reading is possible | `03/25/2026` | Accepted as 25 March 2026 |
| Both numbers equal | `03/03/2026` | Accepted (3 March either way) |
| The month in letters and a four-digit year | `4 March 2026`, `March 4, 2026`, `04-Mar-2026` | Accepted |
| **Both of the first two numbers are 12 or less** | `04/05/2026` | **Refused**: it could be 4 May or 5 April |
| A number in the date column | `45000`, `20250101` (as a number) | **Refused** |
| A two-digit year, a day that does not exist, a year before 1900 or after 2100, or words | `04/05/26`, `31/04/2026`, `soon` | **Refused** |

A refused date is a finding on that row ("Disbursement date is not a valid date: 04/05/2026 could be 4 May 2026 or 5 April 2026: write it as YYYY-MM-DD (2026-05-04 or 2026-04-05) or use a date cell"). The row is marked invalid, the date is not stored, and the institution corrects the file and uploads it again, like any other finding.

## Why the system does not simply choose day-first or month-first
Before this rule, text dates were read month-first without saying so. A date written the way people in Tanzania usually write it (day first), `04/05/2026` for 4 May, was stored as 5 April: a valid-looking date that was wrong, with nothing to show it. A number in a date column was also turned, without a word, into a date of 1970. A date is a financial fact about a loan; a wrong one that looks right is worse than one that is refused with a reason.
The Bank has not chosen a convention, and the system does not choose one for it. Dates that can mean only one thing are accepted; the rest are refused with both readings named. If the Bank decides that every text date is day first, the change is one rule in `app/services/date_rules.py` (the branch for both numbers 12 or less) and its test.

## For institutions: the easy way
In the official template the three date columns (Disbursement Date, Maturity Date, Collateral Pledged Date) are formatted `yyyy-mm-dd`, so a date typed into them is a real date cell shown as typed (2026-11-11, not 11/11/2026). The file then carries real dates and no reading is needed. The example row shows the `YYYY-MM-DD` form.

**If a file is refused with "a number (46337) is not accepted as a date".** The cell holds a plain number, not a date. This happens when a date is pasted as a value into a General or Number cell, or the file was built outside the template (a copy of an older template, another program). Select the column, choose Format Cells, then Date (or Text and type `2026-11-11`), and enter the dates again. An older copy of the template (before this format was added) shows a typed date as 11/11/2026 in the computer's own order; download the template again.
