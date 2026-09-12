"""
MODULE: Tanzania Geography Reference (Region -> District -> Ward -> Village).

Source: 2022 Population and Housing Census village/mtaa list (mainland, 26
regions) + the Zanzibar Frame (5 regions, using "Shehia" terminology for
ward-level units) - both provided directly by the user as the authoritative
source, NOT derived from Wikipedia or any secondary source. This replaces
the earlier, less granular region/district-only reference.

31 regions, 151 districts, 4,342 wards/shehia, 19,946 villages/mitaa/shehia.
"""
import json
import re
from pathlib import Path
from functools import lru_cache

_DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "tanzania_geography.json"


@lru_cache(maxsize=1)
def _load() -> dict:
    with open(_DATA_PATH, encoding="utf-8") as f:
        return json.load(f)


def all_regions() -> list[str]:
    return sorted(_load().keys())


def districts_for_region(region: str) -> list[str]:
    return sorted(_load().get(region, {}).keys())


def wards_for_district(region: str, district: str) -> list[str]:
    return sorted(_load().get(region, {}).get(district, {}).keys())


def villages_for_ward(region: str, district: str, ward: str) -> list[str]:
    return sorted(_load().get(region, {}).get(district, {}).get(ward, []))


def is_valid_region(region: str) -> bool:
    return region in _load()


def is_valid_district(region: str, district: str) -> bool:
    return district in _load().get(region, {})


def is_valid_ward(region: str, district: str, ward: str) -> bool:
    return ward in _load().get(region, {}).get(district, {})


def is_valid_village(region: str, district: str, ward: str, village: str) -> bool:
    return village in _load().get(region, {}).get(district, {}).get(ward, [])


def safe_excel_name(s: str, prefix: str = "") -> str:
    """
    Sanitizes a string into a valid Excel defined-name: letters/digits/
    underscore only, cannot start with a digit, max ~200 chars (Excel's
    actual limit is 255, kept under it for safety with the prefix added).
    """
    clean = re.sub(r"[^A-Za-z0-9_]", "_", s)
    name = f"{prefix}{clean}"[:200]
    if not name or name[0].isdigit():
        name = "_" + name
    return name
