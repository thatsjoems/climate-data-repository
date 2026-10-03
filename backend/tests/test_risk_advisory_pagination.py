"""
Risk Advisory pagination tests (item 9 of the September 2026 external review).

Before this fix, GET /risk-advisories always returned a hard-capped first 200
notes with no way to reach anything older. These tests confirm the endpoint
still behaves exactly as before when `page` is omitted, and that passing
`page` reaches older notes with an accurate X-Total-Count.
"""
from app.models.models import RoleEnum, RiskLevel
from tests.conftest import make_user, login, auth_header


def _publish(client, token, title, risk_level=RiskLevel.MEDIUM.value):
    return client.post(
        "/api/risk-advisories",
        json={"title": title, "risk_level": risk_level, "narrative": "Test narrative."},
        headers=auth_header(token),
    )


def test_list_without_page_returns_a_plain_array_unchanged(client, db_session):
    make_user(db_session, role=RoleEnum.BOT_USER, username="analyst1")
    token = login(client, "analyst1").json()["access_token"]
    _publish(client, token, "Note A")
    _publish(client, token, "Note B")

    res = client.get("/api/risk-advisories", headers=auth_header(token))
    assert res.status_code == 200
    assert isinstance(res.json(), list)
    assert len(res.json()) == 2
    assert "X-Total-Count" not in res.headers


def test_page_parameter_paginates_with_an_accurate_total(client, db_session):
    make_user(db_session, role=RoleEnum.BOT_USER, username="analyst1")
    token = login(client, "analyst1").json()["access_token"]
    for i in range(5):
        _publish(client, token, f"Note {i}")

    res = client.get("/api/risk-advisories?page=1&page_size=2", headers=auth_header(token))
    assert res.status_code == 200
    assert len(res.json()) == 2
    assert res.headers["X-Total-Count"] == "5"

    res2 = client.get("/api/risk-advisories?page=3&page_size=2", headers=auth_header(token))
    assert len(res2.json()) == 1  # 5th, final note
    assert res2.headers["X-Total-Count"] == "5"

    # No overlap between pages 1 and 2
    page1_titles = {n["title"] for n in client.get("/api/risk-advisories?page=1&page_size=2", headers=auth_header(token)).json()}
    page2_titles = {n["title"] for n in client.get("/api/risk-advisories?page=2&page_size=2", headers=auth_header(token)).json()}
    assert page1_titles.isdisjoint(page2_titles)


def test_an_institution_user_cannot_list_risk_advisories(client, db_session):
    make_user(db_session, role=RoleEnum.INSTITUTION_USER, username="inst_user")
    token = login(client, "inst_user").json()["access_token"]
    res = client.get("/api/risk-advisories", headers=auth_header(token))
    assert res.status_code == 403
