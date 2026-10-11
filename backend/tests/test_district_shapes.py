"""
The district outlines for the dashboard's Hazard Summary map: the data file, GET /analytics/district-shapes, and the
map_key that ties a district named in a climate reading to its outline.

The outlines are public boundaries (NBS, 2022 census) and carry no institution data, but they are still only for BOT analysts,
like the rest of the dashboard.
"""
import json
from pathlib import Path

from app.models.models import RoleEnum
from app.api import analytics as analytics_api
from app.services import boundary_service as bs
from tests.conftest import auth_header, login, make_user
from tests.test_hazard_summary import _bot, _reading

SHAPES_FILE = Path(bs.__file__).resolve().parent.parent / "data" / "tanzania_district_shapes.json.gz"


def _outlines():
    return bs.district_shapes()["districts"]


# --------------------------------------------------------------------------------------------- the data
def test_every_district_has_an_outline_made_of_closed_rings_inside_tanzania():
    districts = _outlines()
    assert len(districts) == 150
    for d in districts:
        assert d["rings"], f"{d['region']} / {d['district']} has no outline"
        for ring in d["rings"]:
            assert len(ring) >= 4 and ring[0] == ring[-1]
            for lon, lat in ring:
                assert 29.0 <= lon <= 41.5 and -12.0 <= lat <= -0.9, f"{d['district']}: ({lat}, {lon}) is not in Tanzania"


def test_every_district_of_the_repository_geography_has_an_outline():
    geography = json.loads((Path(bs.__file__).resolve().parent.parent / "data" / "tanzania_geography.json").read_text(encoding="utf-8"))
    missing = [f"{r} / {d}" for r, districts in geography.items() for d in districts if bs.map_key(r.strip(), d.strip()) is None]
    assert missing == []


def test_every_district_has_border_lines_inside_tanzania():
    for d in _outlines():
        assert d["borders"], f"{d['region']} / {d['district']} has no border"
        for line in d["borders"]:
            assert len(line) >= 2
            for lon, lat in line:
                assert 29.0 <= lon <= 41.5 and -12.0 <= lat <= -0.9


def test_the_border_finder_keeps_the_outer_limit_and_drops_the_seam_between_two_wards():
    import importlib.util
    spec = importlib.util.spec_from_file_location("build_boundaries_tool", Path(bs.__file__).resolve().parent.parent.parent / "scripts" / "build_boundaries.py")
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)
    district_borders = tool.district_borders
    left = [[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]
    right = [[1, 0], [2, 0], [2, 1], [1, 1], [1, 0]]          # shares the edge x=1 with `left`
    lines = district_borders([left, right])
    xs = {round(p[0], 3) for line in lines for p in line}
    assert 0 in xs and 2 in xs
    seam = [line for line in lines if all(p[0] == 1 for p in line)]
    assert seam == []


def test_the_file_stays_small_enough_to_send_to_a_browser():
    assert SHAPES_FILE.stat().st_size < 700_000


def test_a_key_does_not_depend_on_capitals_or_spacing_and_an_unknown_place_has_none():
    assert bs.map_key("Dodoma", "Bahi") == "dodoma|bahi"
    assert bs.map_key("  DODOMA ", "bahi ") == "dodoma|bahi"
    assert bs.map_key("Dodoma", "Atlantis") is None
    assert bs.map_key("", "") is None
    assert bs.map_key(None, None) is None


# --------------------------------------------------------------------------------------------- the endpoint
def _get(client, username, path, headers=None):
    token = login(client, username).json()["access_token"]
    return client.get(path, headers={**auth_header(token), **(headers or {})})


def test_a_bot_analyst_gets_every_district_with_a_key_and_may_keep_it(client, db_session):
    _bot(db_session)
    res = _get(client, "bot1", "/api/analytics/district-shapes")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("application/json")
    assert res.headers["cache-control"] == "private, max-age=86400"
    body = res.json()
    assert len(body["districts"]) == 150
    first = body["districts"][0]
    assert set(first) == {"key", "region", "district", "rings", "borders"}
    assert first["key"] == bs.map_key(first["region"], first["district"])


def test_the_outlines_are_sent_compressed_to_a_browser_that_accepts_it_and_plain_to_one_that_does_not(client, db_session):
    _bot(db_session)
    packed = _get(client, "bot1", "/api/analytics/district-shapes", headers={"Accept-Encoding": "gzip"})
    assert packed.headers["content-encoding"] == "gzip"
    assert "accept-encoding" in {v.strip().lower() for v in packed.headers["vary"].split(",")}      # other layers (CORS) may add Origin
    plain = _get(client, "bot1", "/api/analytics/district-shapes", headers={"Accept-Encoding": "identity"})
    assert "content-encoding" not in plain.headers
    assert plain.json() == packed.json()                      # the same districts either way
    assert plain.headers["etag"] != packed.headers["etag"]    # a cached copy of one form is never taken for the other


def test_the_browser_is_told_nothing_changed_when_it_asks_again(client, db_session):
    _bot(db_session)
    first = _get(client, "bot1", "/api/analytics/district-shapes")
    again = _get(client, "bot1", "/api/analytics/district-shapes", headers={"If-None-Match": first.headers["etag"]})
    assert again.status_code == 304
    assert again.content == b""
    other = _get(client, "bot1", "/api/analytics/district-shapes", headers={"If-None-Match": '"something-else"'})
    assert other.status_code == 200


def test_only_a_bot_analyst_may_read_the_outlines(client, db_session):
    _bot(db_session)
    make_user(db_session, role=RoleEnum.SYSTEM_ADMIN, username="admin1")
    make_user(db_session, role=RoleEnum.INSTITUTION_USER, username="inst1")
    assert _get(client, "admin1", "/api/analytics/district-shapes").status_code == 403
    assert _get(client, "inst1", "/api/analytics/district-shapes").status_code == 403
    assert client.get("/api/analytics/district-shapes").status_code in (401, 403)


def test_without_the_file_the_answer_is_not_found_and_nothing_breaks(client, db_session, monkeypatch, tmp_path):
    _bot(db_session)

    def _clear():
        bs.district_shapes.cache_clear()
        bs._shape_keys.cache_clear()
        analytics_api._district_shapes_body.cache_clear()

    monkeypatch.setattr(bs, "_SHAPES_PATH", tmp_path / "missing.json.gz")
    _clear()
    try:
        assert bs.district_shapes() is None
        assert bs.map_key("Dodoma", "Bahi") is None
        assert _get(client, "bot1", "/api/analytics/district-shapes").status_code == 404
    finally:
        monkeypatch.undo()
        _clear()


# --------------------------------------------------------------------------------------------- the hazard summary points at them
def test_each_district_of_the_hazard_summary_carries_the_key_of_its_outline(client, db_session):
    _bot(db_session)
    _reading(db_session, "Dodoma", "Bahi")
    _reading(db_session, "Dodoma", " bahi ", severity="LOW")        # the same district, spelt differently
    _reading(db_session, "Dodoma", "Atlantis")                        # a name the map does not know
    body = _get(client, "bot1", "/api/analytics/hazard-summary?filter_hazard_type=Drought").json()
    keys = {d["district"].strip().lower(): d["map_key"] for d in body["districts"]}
    assert keys["bahi"] == "dodoma|bahi"
    assert keys["atlantis"] is None
