"""
Builds app/data/tanzania_ward_boundaries.json.gz from the National Bureau of Statistics (NBS) shapefile
"2022 Population and Housing Census - Tanzania Wards".

Run it once, by hand, when NBS publishes new boundaries (the result is committed with the application; the
shapefile itself is not, it is 18 MB):

    python scripts/build_boundaries.py path/to/TANZANIA_2022PHC_WARDS_SHAPEFILES.shp

It needs nothing but the Python standard library. What it does to the shapefile:

  1. reads the polygons and the names (region, district, council, ward) from the .shp/.dbf pair;
  2. converts the coordinates from the shapefile's projection (WGS 1984 World Mercator, metres) to latitude and
     longitude in degrees (WGS 84);
  3. drops points that are closer than about 25 m to the straight line between their neighbours (Douglas-Peucker),
     which is far below the 500 m tolerance the validation allows and shrinks the file about tenfold;
  4. stores every ring as a base64 string of 32-bit integers (1e-5 degree, about 1 m, each point as the difference
     from the one before) so the application decodes only the wards it actually looks at;
  5. also writes app/data/tanzania_district_shapes.json.gz: the wards of each district gathered into one shape and
     simplified to about 330 m, which is all the dashboard's district map needs (a few hundred kilobytes).

The names are written exactly as NBS spells them. Matching them to the repository's own geography list is done at
run time (app/services/boundary_service.py); the wards that do not match are listed in docs/COORDINATE_VALIDATION.md.
"""
import argparse
import base64
import gzip
import json
import math
import struct
import sys
from array import array
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "app" / "data"
OUT = DATA / "tanzania_ward_boundaries.json.gz"
OUT_DISTRICTS = DATA / "tanzania_district_shapes.json.gz"
SCALE = 100000            # 1e-5 degree is about 1.1 m
SIMPLIFY_DEGREES = 0.00023  # about 25 m
# The shapes for the dashboard map are drawn on a screen, not used to decide where a point is, so they are far coarser:
MAP_SIMPLIFY_DEGREES = 0.003   # about 330 m
MAP_DECIMALS = 3               # 0.001 degree, about 110 m
BORDER_TOLERANCE = 0.0065      # degrees (~720 m): a ring edge this close to another ring of the same district is inside it

# WGS 84 ellipsoid (the .prj says "WGS_1984_World_Mercator" = EPSG:3395, the ellipsoidal Mercator)
A = 6378137.0
E = 0.0818191908426215


def mercator_to_degrees(x: float, y: float) -> tuple[float, float]:
    lon = math.degrees(x / A)
    phi = math.pi / 2 - 2 * math.atan(math.exp(-y / A))
    for _ in range(8):
        es = E * math.sin(phi)
        phi_new = math.pi / 2 - 2 * math.atan(math.exp(-y / A) * ((1 - es) / (1 + es)) ** (E / 2))
        if abs(phi_new - phi) < 1e-12:
            phi = phi_new
            break
        phi = phi_new
    return math.degrees(phi), lon


def read_dbf(path: Path) -> list[dict]:
    d = path.read_bytes()
    n, header_len, rec_len = struct.unpack("<xxxxIHH", d[:12])
    fields, o = [], 32
    while d[o] != 0x0D:
        fields.append((d[o:o + 11].split(b"\0")[0].decode(), d[o + 16]))
        o += 32
    rows = []
    for i in range(n):
        rec = d[header_len + i * rec_len: header_len + (i + 1) * rec_len]
        o, row = 1, {}
        for name, length in fields:
            row[name] = rec[o:o + length].decode("utf-8", "replace").strip()
            o += length
        rows.append(row)
    return rows


def read_shp(path: Path) -> list[list[list[tuple[float, float]]]]:
    """One entry per record: a list of rings, each a list of (x, y)."""
    d = path.read_bytes()
    shape_type = struct.unpack("<i", d[32:36])[0]
    if shape_type != 5:
        sys.exit(f"Expected polygons (shape type 5), the file has type {shape_type}")
    pos, out = 100, []
    while pos < len(d):
        _, length_words = struct.unpack(">ii", d[pos:pos + 8])
        body = d[pos + 8: pos + 8 + length_words * 2]
        pos += 8 + length_words * 2
        if struct.unpack("<i", body[:4])[0] == 0:
            out.append([])
            continue
        n_parts, n_points = struct.unpack("<ii", body[36:44])
        parts = list(struct.unpack(f"<{n_parts}i", body[44:44 + 4 * n_parts]))
        pts_at = 44 + 4 * n_parts
        pts = struct.unpack(f"<{2 * n_points}d", body[pts_at:pts_at + 16 * n_points])
        coords = [(pts[2 * i], pts[2 * i + 1]) for i in range(n_points)]
        parts.append(n_points)
        out.append([coords[parts[i]:parts[i + 1]] for i in range(n_parts)])
    return out


def simplify(points: list[tuple[float, float]], tol: float) -> list[tuple[float, float]]:
    """Douglas-Peucker on an open polyline, iterative so a long coastline cannot overflow the stack."""
    n = len(points)
    if n < 3:
        return points
    keep = [False] * n
    keep[0] = keep[-1] = True
    stack = [(0, n - 1)]
    tol2 = tol * tol
    while stack:
        a, b = stack.pop()
        ax, ay = points[a]
        bx, by = points[b]
        dx, dy = bx - ax, by - ay
        seg2 = dx * dx + dy * dy
        far, far_d2 = -1, tol2
        for i in range(a + 1, b):
            px, py = points[i]
            if seg2 == 0:
                d2 = (px - ax) ** 2 + (py - ay) ** 2
            else:
                t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / seg2))
                d2 = (px - ax - t * dx) ** 2 + (py - ay - t * dy) ** 2
            if d2 > far_d2:
                far, far_d2 = i, d2
        if far != -1:
            keep[far] = True
            stack.append((a, far))
            stack.append((far, b))
    return [p for p, k in zip(points, keep) if k]


def _seg_dist2(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    s = dx * dx + dy * dy
    t = 0.0 if s == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / s))
    ex, ey = px - ax - t * dx, py - ay - t * dy
    return ex * ex + ey * ey


def district_borders(rings, tol: float = BORDER_TOLERANCE):
    """The outer limit of a district made of many ward rings, as polylines of (lon, lat). The ward data is not topological
    (neighbouring wards do not share vertices), so the outline cannot be found by cancelling shared edges; instead an edge
    of a ring is treated as inside the district when its midpoint lies within `tol` of another ring of the same district."""
    bbox = [(min(p[0] for p in r), min(p[1] for p in r), max(p[0] for p in r), max(p[1] for p in r)) for r in rings]
    near = [[j for j in range(len(rings)) if j != i
             and bbox[j][0] - tol <= bbox[i][2] and bbox[j][2] + tol >= bbox[i][0]
             and bbox[j][1] - tol <= bbox[i][3] and bbox[j][3] + tol >= bbox[i][1]] for i in range(len(rings))]
    out, t2 = [], tol * tol
    for i, r in enumerate(rings):
        cur = []
        for a, b in zip(r, r[1:]):
            mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
            internal = False
            for j in near[i]:
                bb = bbox[j]
                if not (bb[0] - tol <= mx <= bb[2] + tol and bb[1] - tol <= my <= bb[3] + tol):
                    continue
                rj = rings[j]
                if any(_seg_dist2(mx, my, c[0], c[1], d[0], d[1]) <= t2 for c, d in zip(rj, rj[1:])):
                    internal = True
                    break
            if internal:
                if len(cur) > 1:
                    out.append(cur)
                cur = []
            else:
                if not cur:
                    cur = [a]
                cur.append(b)
        if len(cur) > 1:
            out.append(cur)
    return out


def encode_ring(ring: list[tuple[float, float]]) -> str:
    """Closed ring of (lon, lat) degrees -> base64 of int32 pairs, each as the difference from the previous."""
    deltas, px, py = array("i"), 0, 0
    for lon, lat in ring:
        x, y = round(lon * SCALE), round(lat * SCALE)
        deltas.append(x - px)
        deltas.append(y - py)
        px, py = x, y
    if sys.byteorder == "big":
        deltas.byteswap()
    return base64.b64encode(deltas.tobytes()).decode("ascii")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("shp", help="path of TANZANIA_2022PHC_WARDS_SHAPEFILES.shp (the .dbf must sit next to it)")
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--out-districts", default=str(OUT_DISTRICTS))
    a = ap.parse_args()
    shp = Path(a.shp)
    records, shapes = read_dbf(shp.with_suffix(".dbf")), read_shp(shp)
    if len(records) != len(shapes):
        sys.exit(f"The .dbf has {len(records)} rows but the .shp has {len(shapes)} shapes")
    wards, before, after = [], 0, 0
    districts: dict[tuple[str, str], list[list[tuple[float, float]]]] = {}
    for rec, rings in zip(records, shapes):
        enc, minx, miny, maxx, maxy = [], 1e9, 1e9, -1e9, -1e9
        for ring in rings:
            deg = [mercator_to_degrees(x, y)[::-1] for x, y in ring]          # (lon, lat)
            before += len(deg)
            coarse = simplify(deg, MAP_SIMPLIFY_DEGREES)
            if len(coarse) >= 4:
                districts.setdefault((rec["reg_name"], rec["dist_name"]), []).append(coarse)
            else:                                                              # keep a district made only of tiny wards
                districts.setdefault((rec["reg_name"], rec["dist_name"]), [])
            slim = simplify(deg, SIMPLIFY_DEGREES)
            if len(slim) < 4:                                                  # too small to be a polygon
                continue
            after += len(slim)
            for lon, lat in slim:
                minx, maxx, miny, maxy = min(minx, lon), max(maxx, lon), min(miny, lat), max(maxy, lat)
            enc.append(encode_ring(slim))
        if not enc:
            continue
        wards.append({
            "r": rec["reg_name"], "d": rec["dist_name"], "c": rec["counc_code"], "w": rec["ward_name"],
            "b": [round(minx * SCALE), round(miny * SCALE), round(maxx * SCALE), round(maxy * SCALE)],
            "p": enc,
        })
    doc = {
        "source": "National Bureau of Statistics, Tanzania - 2022 Population and Housing Census, Tanzania Wards (shapefile)",
        "scale": SCALE,
        "simplified_to_degrees": SIMPLIFY_DEGREES,
        "wards": wards,
    }
    out = Path(a.out)
    with gzip.open(out, "wt", encoding="utf-8", compresslevel=9) as f:
        json.dump(doc, f, separators=(",", ":"), ensure_ascii=False)
    print(f"{len(wards)} wards, {before:,} points reduced to {after:,}; wrote {out} ({out.stat().st_size / 1e6:.2f} MB)")

    shapes_doc = {
        "source": doc["source"],
        "simplified_to_degrees": MAP_SIMPLIFY_DEGREES,
        "districts": [
            {"r": region, "d": district,
             "rings": [[[round(lon, MAP_DECIMALS), round(lat, MAP_DECIMALS)] for lon, lat in ring] for ring in rings],
             "borders": [[[round(lon, MAP_DECIMALS), round(lat, MAP_DECIMALS)] for lon, lat in line] for line in district_borders(rings)]}
            for (region, district), rings in sorted(districts.items())
        ],
    }
    empty = [f"{r} / {d}" for (r, d), rings in districts.items() if not rings]
    if empty:
        sys.exit(f"These districts have no shape left after simplifying: {empty}; lower MAP_SIMPLIFY_DEGREES")
    out_d = Path(a.out_districts)
    with gzip.open(out_d, "wt", encoding="utf-8", compresslevel=9) as f:
        json.dump(shapes_doc, f, separators=(",", ":"), ensure_ascii=False)
    print(f"{len(districts)} district shapes; wrote {out_d} ({out_d.stat().st_size / 1e3:.0f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
