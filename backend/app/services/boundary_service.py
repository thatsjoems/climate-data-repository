"""
MODULE: Where is a coordinate? Checks a latitude/longitude against the official ward boundaries.

Data: app/data/tanzania_ward_boundaries.json.gz, built by scripts/build_boundaries.py from the National Bureau of
Statistics (NBS) shapefile "2022 Population and Housing Census - Tanzania Wards" (31 regions, 150 districts, 4,344
ward polygons). The shapes are simplified to about 25 m, so a point is accepted when it is inside the ward OR within
BOUNDARY_TOLERANCE_M of it: that covers the simplification, the difference between survey datums and the few metres a
phone's GPS is off, and it means a farm on a ward's edge is never refused.

The one question this module answers is: "the row says region/district/ward X; is the point there?" It never guesses
a place for a point that is nowhere (a lake, the sea, another country): that is reported as "outside", not as a
mismatch, because it cannot tell which place was meant.

  check_location(region, district, ward, lat, lon) -> None                 nothing to check against (no boundary data,
                                                                            or the named place is not in it)
                                                    -> BoundaryFinding     kind "inside", "ward", "district",
                                                                            "region" (the point is in a different
                                                                            ward/district/region) or "outside"
"""
import base64
import gzip
import json
import logging
import math
import re
from array import array
from dataclasses import dataclass
from difflib import SequenceMatcher, get_close_matches
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

_DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "tanzania_ward_boundaries.json.gz"

BOUNDARY_TOLERANCE_M = 500
_METRES_PER_DEGREE = 111_320.0
_CELL = 20_000            # index cell: 0.2 degree, in the file's 1e-5 degree units
_FUZZY_CUTOFF = 0.85


@dataclass(frozen=True)
class Place:
    region: str
    district: str
    ward: str


@dataclass(frozen=True)
class BoundaryFinding:
    # "inside"   the point is in the place the row names (or within the tolerance of it)
    # "ward"     it is in the right district but another ward              -> a warning
    # "district" it is in the right region but another district            -> an error
    # "region"   it is in another region                                   -> an error
    # "outside"  it is in no ward at all (a lake, the sea, another country) -> a warning
    kind: str
    actual: Place | None = None


def _norm(name: str) -> str:
    """Spelling-insensitive form of a place name: case, apostrophes, hyphens, slashes and spacing do not matter."""
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", name.lower().replace("'", "").replace("’", ""))).strip()


class _Ward:
    __slots__ = ("place", "council", "bbox", "_rings", "_decoded")

    def __init__(self, raw: dict):
        self.place = Place(raw["r"], raw["d"], raw["w"])
        self.council = raw["c"]
        self.bbox = tuple(raw["b"])
        self._rings = raw["p"]
        self._decoded = None

    def rings(self) -> list[tuple[array, array]]:
        if self._decoded is None:
            out = []
            for text in self._rings:
                deltas = array("i")
                deltas.frombytes(base64.b64decode(text))
                xs, ys, x, y = array("i"), array("i"), 0, 0
                for i in range(0, len(deltas), 2):
                    x += deltas[i]
                    y += deltas[i + 1]
                    xs.append(x)
                    ys.append(y)
                out.append((xs, ys))
            self._decoded = out
        return self._decoded

    def contains(self, px: float, py: float) -> bool:
        """Even-odd rule over all rings of the ward, so islands and holes are both handled."""
        x0, y0, x1, y1 = self.bbox
        if not (x0 <= px <= x1 and y0 <= py <= y1):
            return False
        inside = False
        for xs, ys in self.rings():
            n = len(xs)
            j = n - 1
            for i in range(n):
                yi, yj = ys[i], ys[j]
                if (yi > py) != (yj > py):
                    if px < (xs[j] - xs[i]) * (py - yi) / (yj - yi) + xs[i]:
                        inside = not inside
                j = i
        return inside

    def distance_m(self, px: float, py: float, scale: int) -> float:
        """Shortest distance from the point to the ward's outline, in metres (flat approximation, fine at 500 m)."""
        kx = _METRES_PER_DEGREE * math.cos(math.radians(py / scale)) / scale
        ky = _METRES_PER_DEGREE / scale
        best = float("inf")
        for xs, ys in self.rings():
            n = len(xs)
            j = n - 1
            for i in range(n):
                ax, ay, bx, by = (xs[j] - px) * kx, (ys[j] - py) * ky, (xs[i] - px) * kx, (ys[i] - py) * ky
                dx, dy = bx - ax, by - ay
                seg2 = dx * dx + dy * dy
                t = 0.0 if seg2 == 0 else max(0.0, min(1.0, -(ax * dx + ay * dy) / seg2))
                d = math.hypot(ax + t * dx, ay + t * dy)
                if d < best:
                    best = d
                j = i
        return best


class _Boundaries:
    def __init__(self, doc: dict):
        self.scale = doc["scale"]
        self.wards = [_Ward(w) for w in doc["wards"]]
        self.grid: dict[tuple[int, int], list[_Ward]] = {}
        self.by_region: dict[str, list[_Ward]] = {}
        self.by_district: dict[tuple[str, str], list[_Ward]] = {}
        self.by_ward: dict[tuple[str, str, str], list[_Ward]] = {}
        self.names: dict[tuple[str, str], list[str]] = {}
        for w in self.wards:
            x0, y0, x1, y1 = w.bbox
            for cx in range(x0 // _CELL, x1 // _CELL + 1):
                for cy in range(y0 // _CELL, y1 // _CELL + 1):
                    self.grid.setdefault((cx, cy), []).append(w)
            r, d, n = _norm(w.place.region), _norm(w.place.district), _norm(w.place.ward)
            self.by_region.setdefault(r, []).append(w)
            self.by_district.setdefault((r, d), []).append(w)
            if (r, d, n) not in self.by_ward:
                self.names.setdefault((r, d), []).append(n)
            self.by_ward.setdefault((r, d, n), []).append(w)

    def candidates(self, px: float, py: float, margin: float = 0.0) -> list[_Ward]:
        out = {}
        for cx in range(int((px - margin) // _CELL), int((px + margin) // _CELL) + 1):
            for cy in range(int((py - margin) // _CELL), int((py + margin) // _CELL) + 1):
                for w in self.grid.get((cx, cy), ()):
                    out[id(w)] = w
        return list(out.values())


@lru_cache(maxsize=1)
def _load() -> _Boundaries | None:
    if not _DATA_PATH.exists():
        logger.warning("Boundary data %s is missing: coordinates are not checked against ward boundaries.", _DATA_PATH)
        return None
    with gzip.open(_DATA_PATH, "rt", encoding="utf-8") as f:
        return _Boundaries(json.load(f))


def is_available() -> bool:
    return _load() is not None


def ward_count() -> int:
    b = _load()
    return len(b.wards) if b else 0


def _in_or_near(wards, px: float, py: float, b: _Boundaries) -> bool:
    margin = BOUNDARY_TOLERANCE_M / _METRES_PER_DEGREE * b.scale
    if any(w.contains(px, py) for w in wards):
        return True
    for w in wards:
        x0, y0, x1, y1 = w.bbox
        if x0 - margin <= px <= x1 + margin and y0 - margin <= py <= y1 + margin:
            if w.distance_m(px, py, b.scale) <= BOUNDARY_TOLERANCE_M:
                return True
    return False


def locate(lat: float, lon: float) -> Place | None:
    """The ward a point is in (or, failing that, the nearest ward within the tolerance); None if it is in no ward."""
    b = _load()
    if b is None:
        return None
    px, py = lon * b.scale, lat * b.scale
    for w in b.candidates(px, py):
        if w.contains(px, py):
            return w.place
    margin = BOUNDARY_TOLERANCE_M / _METRES_PER_DEGREE * b.scale
    nearest, best = None, BOUNDARY_TOLERANCE_M
    for w in b.candidates(px, py, margin):
        d = w.distance_m(px, py, b.scale)
        if d <= best:
            nearest, best = w, d
    return nearest.place if nearest else None


@lru_cache(maxsize=20000)
def _claimed_wards_cached(region: str, district: str, ward: str) -> tuple[str, tuple[_Ward, ...]]:
    level, wards = _claimed_wards(_load(), region, district, ward)
    return level, tuple(wards)


def _claimed_wards(b: _Boundaries, region: str, district: str, ward: str) -> tuple[str, list[_Ward]]:
    """The boundary polygons for the most precise place the row names that the boundary data knows.
    Returns (level, wards) with level "ward", "district", "region" or "" when none of it is known."""
    r, d, n = _norm(region), _norm(district), _norm(ward)
    if r and d and n:
        found = b.by_ward.get((r, d, n))
        if not found:
            close = get_close_matches(n, b.names.get((r, d), []), n=2, cutoff=_FUZZY_CUTOFF)
            # Only an unambiguous near-match is trusted; two equally close names mean we cannot tell which was meant.
            if len(close) == 1 or (len(close) == 2 and _ratio(n, close[0]) - _ratio(n, close[1]) > 0.05):
                found = b.by_ward.get((r, d, close[0]))
        if found:
            return "ward", found
    if r and d and b.by_district.get((r, d)):
        return "district", b.by_district[(r, d)]
    if r and b.by_region.get(r):
        return "region", b.by_region[r]
    return "", []


def _ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def check_location(region: str, district: str, ward: str, lat: float, lon: float) -> BoundaryFinding | None:
    b = _load()
    if b is None:
        return None
    level, wards = _claimed_wards_cached(region, district, ward)
    if not level:
        return None
    px, py = lon * b.scale, lat * b.scale
    if _in_or_near(wards, px, py, b):
        return BoundaryFinding("inside")
    actual = locate(lat, lon)
    if actual is None:
        return BoundaryFinding("outside")
    if _norm(actual.region) != _norm(region):
        return BoundaryFinding("region", actual)
    if _norm(actual.district) != _norm(district):
        return BoundaryFinding("district", actual)
    # Same region and district, so only the ward differs (the named district/region level checks above passed).
    return BoundaryFinding("ward", actual) if level == "ward" else BoundaryFinding("inside")


def hint_for_typing_mistake(region: str, district: str, ward: str, lat: float, lon: float) -> str | None:
    """When a point does not fit the place named, the two commonest slips are a forgotten minus sign on the
    latitude (Tanzania is south of the equator) and latitude and longitude typed the wrong way round. If undoing
    one of them puts the point in the named place, say so."""
    candidates = [
        ("the latitude is missing its minus sign (Tanzania is south of the equator, so it is negative)", -abs(lat), lon),
        ("latitude and longitude look swapped", lon, lat),
        ("latitude and longitude look swapped and the latitude is missing its minus sign", -abs(lon), lat),
    ]
    for text, la, lo in candidates:
        if (la, lo) == (lat, lon) or not (-90 <= la <= 90 and -180 <= lo <= 180):
            continue
        finding = check_location(region, district, ward, la, lo)
        if finding is not None and finding.kind == "inside":
            return f"{text}: ({la}, {lo}) is inside {ward or district or region}"
    return None
