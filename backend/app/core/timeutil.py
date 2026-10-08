"""
The current time in UTC, as the NAIVE datetime this application stores.

datetime.utcnow() is deprecated (it will be removed from Python): it produced a naive UTC value, and so does this, built from the
supported call. Every stored timestamp is naive UTC (the database columns are plain DateTime), so the value is kept exactly the same:
nothing is converted, nothing is stored differently, and values already in the database keep their meaning.
"""
from datetime import datetime, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)
