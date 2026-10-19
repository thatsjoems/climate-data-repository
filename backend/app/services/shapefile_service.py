"""
A Shapefile sent as a ZIP (the Concept Note's upload panel lists "Shapefile .zip") read into the same grid of cells as the Excel template,
so the one validation in validation_service.py serves every format.

Why written here and not with a library. The standard library reads everything this needs (zipfile, struct): a point layer and its attribute table.
A new package would add outside code to a Bank system that handles loan data, and it could not be tested before it is installed. The reader is
therefore small, strict, and has no dependency.

What is accepted. ONE layer of POINTS (Point, PointZ, PointM): the point is where the loan is invested. The attribute table (.dbf) holds the other
columns, named with at most 10 characters (a limit of the DBF format), see SHORT_NAMES. The coordinates of the point become the loan's latitude and
longitude (WGS 84 degrees; a projected system is refused). Lines, polygons and multipoints are refused with a message that says so.

How it is kept safe (a ZIP is an upload that can lie):
* Nothing is ever extracted to disk: every member is read into memory, so a name such as ../../x cannot write anywhere (such names are refused anyway).
* Only the parts of a shapefile are allowed (.shp .shx .dbf .prj .cpg, and the harmless .sbn .sbx .qix .xml); any other member is refused.
* Limits on the number of members, on the size of each member and of all together once unpacked, and on the compression ratio (a "ZIP bomb").
  The sizes written in the ZIP are not believed: the reading itself stops at the limit.
* The number of records is read from the header and refused over the row limit BEFORE any record is read.
* Encrypted members, nested ZIPs and several layers in one ZIP are refused.
"""
import io
import posixpath
import struct
import zipfile

import pandas as pd

from app.services.template_generator import COLUMNS

ALLOWED_SUFFIXES = {".shp", ".shx", ".dbf", ".prj", ".cpg", ".sbn", ".sbx", ".qix", ".xml"}
MAX_MEMBERS = 20
MAX_MEMBER_BYTES = 150 * 1024 * 1024          # one unpacked member
MAX_TOTAL_BYTES = 200 * 1024 * 1024           # all members unpacked (the uploaded ZIP itself is at most 50 MB)
MAX_RATIO = 200                               # unpacked / packed, per member (text tables compress well; a bomb compresses ~1000x)
POINT_TYPES = {1, 11, 21}                     # Point, PointZ, PointM
NULL_TYPE = 0

# The name of each template column in the attribute table (DBF names are at most 10 characters). The full template name is accepted too,
# and a prefix of it when that cut is unique, because some tools shorten names themselves.
SHORT_NAMES: dict[str, str] = {
    "customer_id": "cust_id", "branch_code": "br_code", "branch_name": "br_name", "client_type": "client_typ", "business_size": "biz_size",
    "annual_turnover_tzs": "turnover", "loan_id": "loan_id", "disbursement_date": "disb_date", "maturity_date": "mat_date",
    "currency": "currency", "loan_amount_tzs": "loan_amt", "outstanding_principal_tzs": "out_princ", "annual_interest_rate": "int_rate",
    "loan_type": "loan_type", "loan_economic_activity": "loan_econ", "loan_purpose": "loan_purp", "asset_classification": "asset_cls",
    "region": "region", "district": "district", "ward": "ward", "village": "village",
    "loan_latitude": "loan_lat", "loan_longitude": "loan_lon",
    "collateral_type": "coll_type", "collateral_pledged_date": "coll_date", "collateral_value_tzs": "coll_value",
    "collateral_forced_sale_value_tzs": "coll_fsv", "collateral_economic_activity": "coll_econ",
    "collateral_region": "coll_reg", "collateral_district": "coll_dist", "collateral_ward": "coll_ward", "collateral_village": "coll_vill",
    "collateral_latitude": "coll_lat", "collateral_longitude": "coll_lon",
    "insurance_coverage": "ins_cover", "insurance_policy_type": "ins_type", "insurance_provider_name": "ins_prov",
    "insurance_value_protected_tzs": "ins_value",
}


class ShapefileError(ValueError):
    """The ZIP is not an acceptable shapefile. The message says what is wrong and what to do; it is shown to the person."""


def _field_lookup() -> dict[str, str]:
    """DBF name (lower case) -> template field, for the short names, the full names and the unique 10-character cuts."""
    lookup: dict[str, str] = {}
    cuts: dict[str, list[str]] = {}
    for field, _label in COLUMNS:
        cuts.setdefault(field[:10], []).append(field)
    for field, _label in COLUMNS:
        lookup[field] = field
        if len(cuts[field[:10]]) == 1:
            lookup[field[:10]] = field
    for field, short in SHORT_NAMES.items():
        lookup[short] = field
    return lookup


_LOOKUP = _field_lookup()


def _read_member(zf: zipfile.ZipFile, info: zipfile.ZipInfo, budget: list[int]) -> bytes:
    """The member's bytes, never more than the limits allow, whatever size the ZIP claims. `budget` is the remaining total (one-item list)."""
    limit = min(MAX_MEMBER_BYTES, budget[0])
    with zf.open(info) as handle:
        data = handle.read(limit + 1)
    if len(data) > limit:
        raise ShapefileError("The ZIP is too large once unpacked. Send only the shapefile (.shp, .shx, .dbf, .prj) without other data.")
    if len(data) > 1024 * 1024 and len(data) / max(info.compress_size, 1) > MAX_RATIO:
        raise ShapefileError(f"'{info.filename}' is compressed in an unusual way and was refused. Zip the shapefile again with your GIS software.")
    budget[0] -= len(data)
    return data


def _open_zip(content: bytes) -> dict[str, bytes]:
    """The members of the shapefile, by lower-case suffix (".shp" ...), all checked. Exactly one layer is required."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile:
        raise ShapefileError("This is not a valid ZIP file. Zip the shapefile (.shp, .shx, .dbf and .prj) and try again.")
    with zf:
        infos = [i for i in zf.infolist() if not i.is_dir()]
        if not infos:
            raise ShapefileError("The ZIP file is empty.")
        if len(infos) > MAX_MEMBERS:
            raise ShapefileError(f"The ZIP has {len(infos)} files; a shapefile has at most {MAX_MEMBERS}. Send only the shapefile.")
        layers: dict[str, dict[str, zipfile.ZipInfo]] = {}
        for info in infos:
            name = info.filename.replace("\\", "/")
            if name.startswith("/") or ".." in name.split("/") or ":" in name.split("/")[0]:
                raise ShapefileError(f"The ZIP contains a file with an unsafe name ('{info.filename}') and was refused.")
            if info.flag_bits & 0x1:
                raise ShapefileError("The ZIP is password-protected. Zip the shapefile again without a password.")
            base, suffix = posixpath.splitext(posixpath.basename(name).lower())
            if base.startswith("._") or "__macosx" in name.lower().split("/"):
                continue                                      # the hidden files macOS adds; harmless and never read
            if suffix not in ALLOWED_SUFFIXES:
                raise ShapefileError(f"The ZIP contains '{posixpath.basename(name)}', which is not part of a shapefile. "
                                     "Send only the .shp, .shx, .dbf and .prj files (a .zip inside a .zip is not accepted).")
            if suffix in layers.setdefault(posixpath.join(posixpath.dirname(name), base), {}):
                raise ShapefileError(f"The ZIP contains '{posixpath.basename(name)}' twice.")
            layers[posixpath.join(posixpath.dirname(name), base)][suffix] = info
        layers = {k: v for k, v in layers.items() if ".shp" in v or ".dbf" in v}
        if len(layers) != 1:
            raise ShapefileError("The ZIP must hold exactly ONE shapefile layer (one .shp with its .dbf). "
                                 f"{'None was found' if not layers else f'{len(layers)} were found'}.")
        parts = next(iter(layers.values()))
        for needed in (".shp", ".dbf"):
            if needed not in parts:
                raise ShapefileError(f"The shapefile has no {needed} file. A shapefile needs at least .shp and .dbf (and .prj for the coordinate system).")
        budget = [MAX_TOTAL_BYTES]
        return {suffix: _read_member(zf, info, budget) for suffix, info in parts.items() if suffix in (".shp", ".dbf", ".prj", ".cpg")}


def _check_crs(prj: bytes | None) -> None:
    if not prj:
        return
    text = prj.decode("utf-8", errors="ignore").upper().lstrip()
    if text.startswith("PROJCS") or text.startswith("PROJCRS"):
        raise ShapefileError("The coordinates are in a projected system (metres), not latitude/longitude. In your GIS software export the layer "
                             "in WGS 84 (EPSG:4326) and send it again.")


def _read_points(shp: bytes, expected: int) -> list[tuple[float, float] | None]:
    """(longitude, latitude) of each record, None for a record without a shape. Only point layers are read."""
    if len(shp) < 100 or struct.unpack(">i", shp[:4])[0] != 9994:
        raise ShapefileError("The .shp file is not a valid shapefile.")
    shape_type = struct.unpack("<i", shp[32:36])[0]
    if shape_type not in POINT_TYPES:
        raise ShapefileError("The layer does not hold points. Each loan must be one POINT (where the loan is invested); lines and polygons are not accepted. "
                             "You can also leave the geometry out and give the coordinates in the loan_lat and loan_lon columns of an Excel or CSV file.")
    points: list[tuple[float, float] | None] = []
    pos = 100
    while pos + 8 <= len(shp):
        content_words = struct.unpack(">i", shp[pos + 4:pos + 8])[0]
        end = pos + 8 + content_words * 2
        if content_words < 2 or end > len(shp):
            raise ShapefileError("The .shp file is damaged (a record is cut short).")
        record_type = struct.unpack("<i", shp[pos + 8:pos + 12])[0]
        if record_type == NULL_TYPE:
            points.append(None)
        elif record_type in POINT_TYPES and end - pos - 12 >= 16:
            x, y = struct.unpack("<dd", shp[pos + 12:pos + 28])
            points.append((x, y))
        else:
            raise ShapefileError("The layer mixes shape types. Each record must be a point.")
        pos = end
        if len(points) > expected:
            raise ShapefileError("The .shp has more records than the .dbf table. Export the layer again.")
    if len(points) != expected:
        raise ShapefileError(f"The .shp has {len(points)} records but the .dbf table has {expected}. Export the layer again.")
    return points


def _decode(raw: bytes, encoding: str) -> str:
    try:
        return raw.decode(encoding).strip()
    except (UnicodeDecodeError, LookupError):
        return raw.decode("cp1252", errors="replace").strip()


def _read_table(dbf: bytes, encoding: str, max_rows: int):
    """(field names lower-cased, rows as lists of cell values, deleted flags). Cells are text, number or None."""
    if len(dbf) < 33:
        raise ShapefileError("The .dbf table is not valid.")
    n_records, header_len, record_len = struct.unpack("<IHH", dbf[4:12])
    if n_records > max_rows:
        raise ShapefileError(f"This shapefile has {n_records} records, which exceeds the maximum of {max_rows} allowed per submission. "
                             "Please split it into smaller files.")
    fields = []
    pos = 32
    while pos + 32 <= len(dbf) and dbf[pos] != 0x0D:
        name = dbf[pos:pos + 11].split(b"\x00")[0].decode("ascii", errors="ignore").strip().lower()
        fields.append((name, chr(dbf[pos + 11]), dbf[pos + 16], dbf[pos + 17]))
        pos += 32
    if not fields or sum(f[2] for f in fields) + 1 != record_len or header_len + n_records * record_len > len(dbf) + 1:
        raise ShapefileError("The .dbf table is damaged or incomplete. Export the layer again.")
    rows, deleted = [], []
    for i in range(n_records):
        start = header_len + i * record_len
        rec = dbf[start:start + record_len]
        deleted.append(rec[:1] == b"*")
        cells, offset = [], 1
        for _name, ftype, length, _dec in fields:
            raw = rec[offset:offset + length]
            offset += length
            text = _decode(raw, encoding)
            if text == "" or ftype in ("M", "B", "G", "P"):
                cells.append(None)
            elif ftype in ("N", "F"):
                try:
                    number = float(text)
                    cells.append(int(number) if number.is_integer() and "." not in text else number)
                except ValueError:
                    cells.append(text)                       # left as text: the validation reports it as an invalid number
            elif ftype == "D":
                cells.append(f"{text[:4]}-{text[4:6]}-{text[6:8]}" if len(text) == 8 and text.isdigit() else text)
            elif ftype == "L":
                cells.append({"Y": "Yes", "T": "Yes", "N": "No", "F": "No"}.get(text.upper(), None))
            else:
                cells.append(text)
        rows.append(cells)
    return [f[0] for f in fields], rows, deleted


def shapefile_zip_as_frame(content: bytes, max_rows: int = 100000) -> pd.DataFrame:
    """The shapefile ZIP as the raw grid the validation reads from an Excel sheet: a header row of the template's labels, then one row per loan."""
    parts = _open_zip(content)
    _check_crs(parts.get(".prj"))
    encoding = _decode(parts[".cpg"], "ascii").lower() if ".cpg" in parts else "utf-8"
    names, rows, deleted = _read_table(parts[".dbf"], encoding or "utf-8", max_rows)
    points = _read_points(parts[".shp"], len(rows))

    index_of = {}
    for col, name in enumerate(names):
        field = _LOOKUP.get(name)
        if field is not None and field not in index_of:
            index_of[field] = col
    unknown = [n for n in names if n not in _LOOKUP]

    fields = [f for f, _ in COLUMNS]
    grid: list[list] = [[label for _f, label in COLUMNS]]
    for row, point, is_deleted in zip(rows, points, deleted):
        if is_deleted:
            continue
        line = [row[index_of[f]] if f in index_of else None for f in fields]
        if point is not None:
            line[fields.index("loan_longitude")], line[fields.index("loan_latitude")] = point   # the position of the point is the loan's location
        grid.append(line)
    frame = pd.DataFrame(grid, dtype=object)
    frame.attrs["unrecognised_columns"] = unknown
    return frame

