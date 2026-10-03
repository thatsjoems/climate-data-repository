"""
Admin self-lockout protection (KG-03, closed during an admin-side review,
then corrected here after a real test run).

Only self-deactivation needs to be blocked. Whoever is authenticated enough
to call this endpoint is themselves necessarily active right now (a
deactivated account is rejected by the per-request authentication check
before any endpoint body runs), so refusing self-deactivation alone
guarantees at least one active administrator - the caller - survives every
call. An earlier version of this fix ALSO tried to block deactivating "the
last other active admin" by counting active admins besides the target; a
real test run showed that branch could never actually fire (assert 200 ==
400): the caller always satisfies its own count, since they cannot have
deactivated themselves. That branch was removed as unreachable code rather
than kept to defend against a state the API cannot produce.
"""
from app.models.models import RoleEnum
from tests.conftest import make_user, login, auth_header


def test_admin_cannot_deactivate_own_account(client, db_session):
    make_user(db_session, role=RoleEnum.SYSTEM_ADMIN, username="admin1")
    token = login(client, "admin1").json()["access_token"]
    admin1_id = client.get("/api/auth/me", headers=auth_header(token)).json()["id"]

    res = client.patch(f"/api/users/{admin1_id}/deactivate", headers=auth_header(token))
    assert res.status_code == 400
    assert "own account" in res.json()["detail"].lower()


def test_admin_can_deactivate_another_admin_when_a_third_remains_active(client, db_session):
    make_user(db_session, role=RoleEnum.SYSTEM_ADMIN, username="admin1")
    admin2 = make_user(db_session, role=RoleEnum.SYSTEM_ADMIN, username="admin2")
    token = login(client, "admin1").json()["access_token"]

    res = client.patch(f"/api/users/{admin2.id}/deactivate", headers=auth_header(token))
    assert res.status_code == 200
    assert res.json()["is_active"] is False


def test_admin_can_deactivate_the_only_other_admin_leaving_the_caller_active(client, db_session):
    """
    With exactly two admins, the caller deactivating the other one is
    perfectly safe - the caller themselves remains active, so the system
    is never left without an administrator. This is the corrected version
    of a test that previously (and incorrectly) expected this to be
    refused, after a real run showed the expectation itself was wrong,
    not the application code.
    """
    make_user(db_session, role=RoleEnum.SYSTEM_ADMIN, username="admin1")
    admin2 = make_user(db_session, role=RoleEnum.SYSTEM_ADMIN, username="admin2")
    token = login(client, "admin1").json()["access_token"]

    res = client.patch(f"/api/users/{admin2.id}/deactivate", headers=auth_header(token))
    assert res.status_code == 200

    # admin1 (the caller) remains active and able to administer the system
    me = client.get("/api/auth/me", headers=auth_header(token))
    assert me.status_code == 200
    assert me.json()["is_active"] is True

    # and admin1 still cannot deactivate themselves, even now that they are
    # the only active admin - this is what actually prevents total lockout
    admin1_id = me.json()["id"]
    res2 = client.patch(f"/api/users/{admin1_id}/deactivate", headers=auth_header(token))
    assert res2.status_code == 400


def test_non_admin_role_deactivation_is_unaffected_by_the_admin_check(client, db_session):
    make_user(db_session, role=RoleEnum.SYSTEM_ADMIN, username="admin1")
    bot_user = make_user(db_session, role=RoleEnum.BOT_USER, username="analyst1")
    token = login(client, "admin1").json()["access_token"]

    res = client.patch(f"/api/users/{bot_user.id}/deactivate", headers=auth_header(token))
    assert res.status_code == 200
    assert res.json()["is_active"] is False
