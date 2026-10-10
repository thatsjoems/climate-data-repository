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
     from the one before) so the application decodes only the wards it actually looks at.

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

OUT = Path(__file__).resolve().parent.parent / "app" / "data" / "tanzania_ward_boundaries.json.gz"
SCALE = 100000            # 1e-5 degree is about 1.1 m
SIMPLIFY_DEGREES = 0.00023  # about 25 m

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
    a = ap.parse_args()
    shp = Path(a.shp)
    records, shapes = read_dbf(shp.with_suffix(".dbf")), read_shp(shp)
    if len(records) != len(shapes):
        sys.exit(f"The .dbf has {len(records)} rows but the .shp has {len(shapes)} shapes")
    wards, before, after = [], 0, 0
    for rec, rings in zip(records, shapes):
        enc, minx, miny, maxx, maxy = [], 1e9, 1e9, -1e9, -1e9
        for ring in rings:
            deg = [mercator_to_degrees(x, y)[::-1] for x, y in ring]          # (lon, lat)
            before += len(deg)
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
    return 0


if __name__ == "__main__":
    sys.exit(main())
