"""
How a date written in an uploaded file is read.

Why this exists. A date typed as text, such as 04/05/2026, can mean 4 May or 5 April, and the library that used to read it assumed the month comes first
without saying so, so a date written the way people in Tanzania write it (day first) could be stored as a different, valid-looking date. A NUMBER in a date column
(45000, 20250101) was turned into a date of 1970, also without a word. Nothing in the data then showed that anything was wrong. A date is a financial fact about a
loan; a wrong one that looks right is worse than one that is refused with a reason.

The rules (no guess is made where the Bank has not chosen, and every refusal says what to do):
* A real date cell of the spreadsheet is always accepted.
* Year first (2026-03-15, 2026/03/15, 2026.03.15, 20260315): unambiguous, accepted. The time of day, if any, is dropped.
* Three numbers with the year LAST (04/05/2026, 25-03-2026): accepted only when they can mean one thing, that is when one of the first two is above 12
  (25/03/2026 is 25 March; 03/25/2026 is 25 March) or both are equal (03/03/2026). When both are 12 or less it is AMBIGUOUS and is refused, naming both
  readings.
* A month written in letters with a four-digit year (4 March 2026, March 4 2026, 04-Mar-2026): accepted.
* A number (including 45000 or 20250101 as a number), a two-digit year, a year before 1900 or after 2100, or anything else: refused.
Refused dates are findings on the row, like any other invalid value, so the institution fixes the file; they are never stored.
"""
import numbers
import re
from datetime import date, datetime

import pandas as pd

MIN_YEAR, MAX_YEAR = 1900, 2100

_YEAR_FIRST = re.compile(r"^(\d{4})[/.\-](\d{1,2})[/.\-](\d{1,2})(?:[ T]\d{1,2}:\d{2}(?::\d{2}(?:\.\d+)?)?)?$")
_COMPACT = re.compile(r"^(\d{4})(\d{2})(\d{2})$")
_YEAR_LAST = re.compile(r"^(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4})$")
_FOUR_DIGIT_YEAR = re.compile(r"(?<!\d)\d{4}(?!\d)")
_MONTH_NAME = re.compile(r"[A-Za-z]{3,}")

EMPTY, OK, AMBIGUOUS, INVALID = "empty", "ok", "ambiguous", "invalid"


def _build(year: int, month: int, day: int):
    if not (MIN_YEAR <= year <= MAX_YEAR):
        return None
    try:
        return date(year, month, day)
    except ValueError:
        return None


def read_date(value):
    """(the date or None, one of EMPTY, OK, AMBIGUOUS, INVALID)."""
    if value is None or pd.isna(value):
        return None, EMPTY
    if isinstance(value, bool):
        return None, INVALID
    if isinstance(value, (datetime, date)):                       # a real date cell (pandas Timestamp is a datetime)
        as_date = value.date() if isinstance(value, datetime) else value
        return (as_date, OK) if MIN_YEAR <= as_date.year <= MAX_YEAR else (None, INVALID)
    if isinstance(value, numbers.Real):                           # 45000, 20250101, 2026.0: not a date, whatever it looks like
        return None, INVALID
    if not isinstance(value, str):
        return None, INVALID

    text = value.strip()
    if text == "" or text.lower() == "nan":
        return None, EMPTY

    m = _YEAR_FIRST.match(text) or _COMPACT.match(text)
    if m:
        built = _build(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        return (built, OK) if built else (None, INVALID)

    m = _YEAR_LAST.match(text)
    if m:
        a, b, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if a > 12 and b <= 12:                                    # 25/03/2026: day first, the only possible reading
            built = _build(year, b, a)
        elif b > 12 and a <= 12:                                  # 03/25/2026: month first, the only possible reading
            built = _build(year, a, b)
        elif a == b and a <= 12:                                  # 03/03/2026: the same either way
            built = _build(year, a, b)
        elif a <= 12 and b <= 12:
            return None, AMBIGUOUS
        else:
            return None, INVALID
        return (built, OK) if built else (None, INVALID)

    if _MONTH_NAME.search(text) and _FOUR_DIGIT_YEAR.search(text):    # a month in letters and a full year: nothing to guess
        try:
            parsed = pd.to_datetime(text, errors="raise")
        except (TypeError, ValueError, OverflowError):
            return None, INVALID
        if pd.isna(parsed):
            return None, INVALID
        built = _build(parsed.year, parsed.month, parsed.day)
        return (built, OK) if built else (None, INVALID)
    return None, INVALID


def date_problem_hint(value) -> str:
    """What to tell the institution about a date that was refused ('' when there is nothing to add)."""
    parsed, status = read_date(value)
    if status in (EMPTY, OK):
        return ""
    how = "write it as YYYY-MM-DD (for example 2026-03-15) or use a date cell"
    if status == AMBIGUOUS:
        m = _YEAR_LAST.match(str(value).strip())
        a, b, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        day_first, month_first = _build(year, b, a), _build(year, a, b)
        if day_first and month_first:
            return (f"{str(value).strip()} could be {day_first.day} {day_first.strftime('%B %Y')} or {month_first.day} {month_first.strftime('%B %Y')}: "
                    f"{how} ({day_first.isoformat()} or {month_first.isoformat()})")
    if isinstance(value, numbers.Real) and not isinstance(value, bool):
        shown = int(value) if float(value).is_integer() else value
        return f"a number ({shown}) is not accepted as a date: {how}"
    return how
