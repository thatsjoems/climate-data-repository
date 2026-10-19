"""Builds a small shapefile ZIP in memory for the tests (points + attribute table), with the standard library only."""
import io
import struct
import zipfile

from app.services.shapefile_service import SHORT_NAMES


def _dbf(rows: list[dict], fields: list[str], encoding="utf-8") -> bytes:
    width = 60
    header_len = 32 + 32 * len(fields) + 1
    record_len = 1 + width * len(fields)
    out = bytearray(struct.pack("<BBBBIHH", 3, 26, 10, 11, len(rows), header_len, record_len) + b"\x00" * 20)
    for name in fields:
        out += name.encode("ascii").ljust(11, b"\x00") + b"C" + b"\x00" * 4 + bytes([width, 0]) + b"\x00" * 14
    out += b"\x0d"
    for row in rows:
        out += b" "
        for name in fields:
            out += str("" if row.get(name) is None else row.get(name)).encode(encoding).ljust(width)[:width]
    out += b"\x1a"
    return bytes(out)


def _shp(points: list[tuple[float, float] | None], shape_type=1) -> bytes:
    records = bytearray()
    for i, p in enumerate(points, start=1):
        if p is None:
            content = struct.pack("<i", 0)
        else:
            content = struct.pack("<idd", shape_type, p[0], p[1])
        records += struct.pack(">ii", i, len(content) // 2) + content
    header = struct.pack(">i", 9994) + b"\x00" * 20 + struct.pack(">i", (100 + len(records)) // 2) + struct.pack("<ii", 1000, shape_type) + b"\x00" * 64
    return header + bytes(records)


def build_shapefile_zip(rows: list[dict], points, extra_members: dict | None = None, shape_type=1, prj: str | None = 'GEOGCS["GCS_WGS_1984"]',
                        encoding="utf-8", cpg: str | None = None, short_names=True) -> bytes:
    """rows are keyed by the template field names (as in VALID_ROW); they are written under their short DBF names."""
    names = {f: (SHORT_NAMES[f] if short_names else f) for r in rows for f in r}
    fields = list(dict.fromkeys(names.values()))
    dbf_rows = [{names[f]: v for f, v in r.items()} for r in rows]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("loans.shp", _shp(points, shape_type))
        zf.writestr("loans.shx", b"\x00" * 100)
        zf.writestr("loans.dbf", _dbf(dbf_rows, fields, encoding))
        if prj is not None:
            zf.writestr("loans.prj", prj)
        if cpg:
            zf.writestr("loans.cpg", cpg)
        for name, data in (extra_members or {}).items():
            zf.writestr(name, data)
    return buf.getvalue()
