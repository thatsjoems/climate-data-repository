"""
System monitoring (app/services/monitoring_service.py, app/services/monitor_loop.py, GET /api/system/status).

Each check is exercised on its own with the inputs spelled out (a backup of 3 hours, a disk 8% free, 12 failed sign-ins in the last hour),
including the edges: exactly at a limit, in the future, unreadable, missing. Then the things that make the alerts usable: who is told, that a
repeated alert is not repeated, that a change of severity is told at once, that a check which fails does not break the page, and that nobody
but the System Administrator can read the status.
"""
import asyncio
import json
import types
from datetime import timedelta

import pytest

from app.core.config import settings
from app.core.timeutil import utcnow
from app.models.models import ApiClient, AuditLog, Notification, RoleEnum
from app.services import monitor_loop
from app.services import monitoring_service as m
from tests.conftest import auth_header, login, make_user

NOW = utcnow().replace(microsecond=0)      # whole seconds, as the backup stamp is: "exactly 26 hours old" must be exactly that


# ------------------------------------------------------------------ backups
def _status(folder, taken, **over):
    data = {"taken_utc": taken.strftime("%Y%m%dT%H%M%SZ"), "result": "OK", "revision": "f3a7c1e5b829", "database_bytes": 1000,
            "uploads_bytes": 10, "off_machine": True, "copy_error": None}
    data.update(over)
    (folder / "last_backup.json").write_text(json.dumps(data), encoding="utf-8")
    return folder


def test_no_backup_recorded_is_urgent_in_production_and_only_information_elsewhere(tmp_path):
    assert m.check_backup(tmp_path, NOW, 26, production=True).status == "CRITICAL"
    assert m.check_backup(tmp_path / "missing", NOW, 26, production=True).status == "CRITICAL"
    assert m.check_backup(tmp_path, NOW, 26, production=False).status == "INFO"


def test_a_fresh_backup_that_was_copied_off_the_machine_is_ok(tmp_path):
    check = m.check_backup(_status(tmp_path, NOW - timedelta(hours=3)), NOW, 26, True)
    assert check.status == "OK" and check.details["age_hours"] == 3.0 and check.details["off_machine_copy"] is True


@pytest.mark.parametrize("hours, expected", [(25.9, "OK"), (26.0, "OK"), (26.5, "CRITICAL"), (72, "CRITICAL")])
def test_a_backup_older_than_the_limit_is_urgent(tmp_path, hours, expected):
    assert m.check_backup(_status(tmp_path, NOW - timedelta(hours=hours)), NOW, 26, True).status == expected


def test_a_backup_that_could_not_be_copied_off_the_machine_is_attention_and_says_why(tmp_path):
    check = m.check_backup(_status(tmp_path, NOW - timedelta(hours=2), result="COPY-FAILED", off_machine=False, copy_error="cannot write to D:"), NOW, 26, True)
    assert check.status == "WARN" and "cannot write to D:" in check.message


def test_a_backup_that_was_never_copied_off_the_machine_is_attention(tmp_path):
    check = m.check_backup(_status(tmp_path, NOW - timedelta(hours=2), off_machine=False), NOW, 26, True)
    assert check.status == "WARN" and "off-machine" in check.message


@pytest.mark.parametrize("content", ["not json at all", "{}", json.dumps({"taken_utc": "yesterday"})])
def test_an_unreadable_status_file_is_urgent_not_an_error(tmp_path, content):
    (tmp_path / "last_backup.json").write_text(content, encoding="utf-8")
    assert m.check_backup(tmp_path, NOW, 26, True).status == "CRITICAL"


def test_a_backup_dated_in_the_future_is_not_an_error(tmp_path):
    assert m.check_backup(_status(tmp_path, NOW + timedelta(hours=2)), NOW, 26, True).status == "OK"


# ------------------------------------------------------------------ disk
@pytest.mark.parametrize("free_percent, expected", [(50, "OK"), (20, "OK"), (19.9, "WARN"), (10, "WARN"), (9.9, "CRITICAL"), (0, "CRITICAL")])
def test_disk_space_levels(free_percent, expected):
    assert m.check_disk(1000, int(free_percent * 10), 20, 10).status == expected


def test_a_disk_of_unknown_size_is_not_a_division_by_zero():
    assert m.check_disk(0, 0, 20, 10).status == "CRITICAL"


# ------------------------------------------------------------------ attacks
def _audit(db, action, when, entity="u1", details=None):
    db.add(AuditLog(action=action, entity_type="User", entity_id=entity, created_at=when, details_json=details))


def test_failed_signins_are_counted_over_the_last_hour_only(db_session):
    for i in range(12):
        _audit(db_session, "LOGIN_FAILED", NOW - timedelta(minutes=5 + i), entity=f"user{i % 4}")
    for i in range(50):
        _audit(db_session, "LOGIN_FAILED", NOW - timedelta(hours=2), entity="old")
    db_session.commit()
    check = m.check_signins(db_session, NOW, 10, 30)
    assert check.status == "WARN" and check.details["failed_last_hour"] == 12 and check.details["accounts_targeted_last_hour"] == 4
    assert check.details["failed_last_24_hours"] == 62


@pytest.mark.parametrize("failures, expected", [(0, "OK"), (9, "OK"), (10, "WARN"), (29, "WARN"), (30, "CRITICAL")])
def test_failed_signin_levels(db_session, failures, expected):
    for i in range(failures):
        _audit(db_session, "MFA_FAILED" if i % 2 else "LOGIN_FAILED", NOW - timedelta(minutes=1))
    db_session.commit()
    assert m.check_signins(db_session, NOW, 10, 30).status == expected


@pytest.mark.parametrize("lockouts, expected", [(1, "OK"), (2, "WARN"), (4, "WARN"), (5, "CRITICAL")])
def test_several_accounts_locked_within_an_hour_is_noticed_even_if_failures_are_few(db_session, lockouts, expected):
    for i in range(lockouts):
        _audit(db_session, "LOGIN_LOCKED", NOW - timedelta(minutes=10), entity=f"user{i}")
    db_session.commit()
    assert m.check_signins(db_session, NOW, 1000, 1000).status == expected


@pytest.mark.parametrize("refused, expected", [(5, "OK"), (20, "WARN"), (100, "CRITICAL")])
def test_refused_api_keys_levels_and_reasons(db_session, refused, expected):
    for i in range(refused):
        _audit(db_session, "INTEGRATION_AUTH_FAILED", NOW - timedelta(minutes=3), details={"reason": "revoked" if i % 2 else "wrong secret"})
    _audit(db_session, "INTEGRATION_AUTH_FAILED", NOW - timedelta(hours=3), details={"reason": "too old to count"})
    db_session.commit()
    check = m.check_key_failures(db_session, NOW)
    assert check.status == expected and check.details["refused_last_hour"] == refused and "too old to count" not in check.details["by_reason"]


@pytest.mark.parametrize("locked, expected", [(0, "OK"), (2, "OK"), (3, "WARN")])
def test_accounts_locked_at_the_moment(db_session, locked, expected):
    for i in range(locked):
        make_user(db_session, role=RoleEnum.BOT_USER, username=f"locked{i}").locked_until = NOW + timedelta(minutes=10)
    make_user(db_session, role=RoleEnum.BOT_USER, username="was_locked").locked_until = NOW - timedelta(minutes=10)     # the lock has ended
    db_session.commit()
    assert m.check_locked_accounts(db_session, NOW).status == expected


# ------------------------------------------------------------------ keys and administrators
def _key(db, owner, name, prefix, created, expires, revoked=None):
    db.add(ApiClient(name=name, key_prefix=prefix, key_hash="0" * 64, created_by_user_id=owner.id, created_at=created, expires_at=expires,
                     revoked_at=revoked, revoked_by_user_id=owner.id if revoked else None))
    db.commit()


def test_a_key_about_to_expire_is_attention_and_named(db_session):
    owner = make_user(db_session, role=RoleEnum.BOT_USER, username="owner1")
    _key(db_session, owner, "TMA feed", "aaaaaaaaaa", NOW - timedelta(days=100), NOW + timedelta(days=5))
    check = m.check_keys(db_session, NOW)
    assert check.status == "WARN" and "TMA feed" in check.message and "cdrk_" not in check.message


def test_a_key_that_expired_recently_without_being_revoked_is_attention(db_session):
    owner = make_user(db_session, role=RoleEnum.BOT_USER, username="owner2")
    _key(db_session, owner, "PMO feed", "bbbbbbbbbb", NOW - timedelta(days=200), NOW - timedelta(days=3))
    check = m.check_keys(db_session, NOW)
    assert check.status == "WARN" and "PMO feed" in check.message and "refused" in check.message


def test_revoked_far_and_long_expired_keys_are_not_a_worry(db_session):
    owner = make_user(db_session, role=RoleEnum.BOT_USER, username="owner3")
    _key(db_session, owner, "revoked soon", "cccccccccc", NOW - timedelta(days=10), NOW + timedelta(days=3), revoked=NOW - timedelta(days=1))
    _key(db_session, owner, "far away", "dddddddddd", NOW - timedelta(days=10), NOW + timedelta(days=40))
    _key(db_session, owner, "long gone", "eeeeeeeeee", NOW - timedelta(days=400), NOW - timedelta(days=60))
    assert m.check_keys(db_session, NOW).status == "OK"


@pytest.mark.parametrize("admins, expected", [(0, "CRITICAL"), (1, "WARN"), (2, "OK")])
def test_the_number_of_active_administrators(db_session, admins, expected):
    for i in range(admins):
        make_user(db_session, role=RoleEnum.SYSTEM_ADMIN, username=f"adm{i}")
    inactive = make_user(db_session, role=RoleEnum.SYSTEM_ADMIN, username="adm_inactive")
    inactive.is_active = False
    db_session.commit()
    assert m.check_administrators(db_session).status == expected


# ------------------------------------------------------------------ database and schema
def test_the_database_check_reports_how_fast_it_answers(db_session):
    check = m.check_database(db_session)
    assert check.status in ("OK", "WARN") and check.details["response_ms"] >= 0


def test_a_database_not_built_by_the_migrations_is_information_not_an_error(db_session):
    assert m.check_schema(db_session).status == "INFO"


@pytest.mark.parametrize("current, head, expected", [("abc", "abc", "OK"), ("abc", "def", "CRITICAL")])
def test_the_schema_version_must_match_the_application(db_session, monkeypatch, current, head, expected):
    monkeypatch.setattr(m, "sa_inspect", lambda bind: types.SimpleNamespace(has_table=lambda name: True))
    monkeypatch.setattr(m, "current_revision", lambda db: current)
    monkeypatch.setattr(m, "head_revision", lambda: head)
    assert m.check_schema(db_session).status == expected


# ------------------------------------------------------------------ all together
EXPECTED_KEYS = ["database", "schema", "backup", "disk", "signins", "key_failures", "locked_accounts", "keys", "administrators"]


def test_every_check_reports_and_one_that_fails_does_not_break_the_others(db_session, monkeypatch):
    def broken(db, now):
        raise RuntimeError("secret detail that must not reach the page")

    monkeypatch.setattr(m, "check_locked_accounts", broken)
    checks = m.run_checks(db_session)
    assert [c.key for c in checks] == EXPECTED_KEYS
    failed = next(c for c in checks if c.key == "locked_accounts")
    assert failed.status == "WARN" and "could not be checked" in failed.message and "secret detail" not in failed.message


def test_the_overall_state_is_the_worst_one_and_information_never_counts():
    C = m.Check
    assert m.overall([C("a", "A", "OK", ""), C("b", "B", "INFO", "")]) == "OK"
    assert m.overall([C("a", "A", "OK", ""), C("b", "B", "WARN", "")]) == "WARN"
    assert m.overall([C("a", "A", "WARN", ""), C("b", "B", "CRITICAL", "")]) == "CRITICAL"
    assert m.overall([]) == "OK"


@pytest.mark.parametrize("statuses, code", [(["OK", "INFO"], 0), (["OK", "WARN"], 1), (["WARN", "CRITICAL"], 2)])
def test_the_exit_code_for_the_hosts_own_monitoring(statuses, code):
    assert m.exit_code([m.Check(str(i), "T", s, "") for i, s in enumerate(statuses)]) == code


# ------------------------------------------------------------------ who is told, and how often
def _alerts(db):
    return db.query(Notification).filter_by(type="SYSTEM_ALERT").all()


def test_alerts_go_to_every_active_administrator_and_nobody_else(db_session):
    a1 = make_user(db_session, role=RoleEnum.SYSTEM_ADMIN, username="alert_a1")
    a2 = make_user(db_session, role=RoleEnum.SYSTEM_ADMIN, username="alert_a2")
    gone = make_user(db_session, role=RoleEnum.SYSTEM_ADMIN, username="alert_gone")
    gone.is_active = False
    make_user(db_session, role=RoleEnum.BOT_USER, username="alert_bot")
    db_session.commit()
    checks = [m.Check("backup", "Backups", "CRITICAL", "no backup"), m.Check("disk", "Disk space", "OK", "fine"),
              m.Check("schema", "Schema", "INFO", "n/a"), m.Check("keys", "API keys", "WARN", "one expires")]
    assert m.notify_admins(db_session, checks, NOW) == 4                          # two alerts, two administrators
    assert {n.user_id for n in _alerts(db_session)} == {a1.id, a2.id}
    assert all(n.message.startswith("[CRITICAL]") or n.message.startswith("[WARN]") for n in _alerts(db_session))


def test_an_alert_is_not_repeated_until_its_time_has_passed(db_session):
    make_user(db_session, role=RoleEnum.SYSTEM_ADMIN, username="alert_one")
    urgent, attention = m.Check("backup", "Backups", "CRITICAL", "x"), m.Check("keys", "API keys", "WARN", "y")
    assert m.notify_admins(db_session, [urgent, attention], NOW) == 2
    assert m.notify_admins(db_session, [urgent, attention], NOW + timedelta(hours=1)) == 0              # told an hour ago
    assert m.notify_admins(db_session, [urgent, attention], NOW + timedelta(hours=25)) == 1             # urgent again after a day, attention not yet
    assert m.notify_admins(db_session, [urgent, attention], NOW + timedelta(days=8)) == 2


def test_a_change_of_severity_is_told_at_once(db_session):
    make_user(db_session, role=RoleEnum.SYSTEM_ADMIN, username="alert_two")
    assert m.notify_admins(db_session, [m.Check("disk", "Disk space", "WARN", "low")], NOW) == 1
    assert m.notify_admins(db_session, [m.Check("disk", "Disk space", "CRITICAL", "very low")], NOW + timedelta(minutes=10)) == 1


def test_a_notification_never_overflows_its_column(db_session):
    make_user(db_session, role=RoleEnum.SYSTEM_ADMIN, username="alert_three")
    m.notify_admins(db_session, [m.Check("backup", "Backups", "CRITICAL", "x" * 2000)], NOW)
    assert len(_alerts(db_session)[0].message) <= 500


# ------------------------------------------------------------------ the page
def test_only_the_system_administrator_may_read_the_status(client, db_session):
    for name, role in (("st_admin", RoleEnum.SYSTEM_ADMIN), ("st_bot", RoleEnum.BOT_USER), ("st_inst", RoleEnum.INSTITUTION_USER)):
        make_user(db_session, role=role, username=name)
    assert client.get("/api/system/status").status_code == 401
    assert client.get("/api/system/status", headers=auth_header(login(client, "st_admin").json()["access_token"])).status_code == 200
    assert client.get("/api/system/status", headers=auth_header(login(client, "st_bot").json()["access_token"])).status_code == 403
    assert client.get("/api/system/status", headers=auth_header(login(client, "st_inst").json()["access_token"])).status_code == 403


def test_the_status_has_the_expected_shape_and_shows_no_secret(client, db_session):
    make_user(db_session, role=RoleEnum.SYSTEM_ADMIN, username="st_shape")
    owner = make_user(db_session, role=RoleEnum.BOT_USER, username="st_owner")
    _key(db_session, owner, "TMA feed", "ffffffffff", NOW - timedelta(days=100), NOW + timedelta(days=5))
    body = client.get("/api/system/status", headers=auth_header(login(client, "st_shape").json()["access_token"])).json()
    assert [c["key"] for c in body["checks"]] == EXPECTED_KEYS
    assert body["overall"] in ("OK", "WARN", "CRITICAL") and sum(body["counts"].values()) == len(EXPECTED_KEYS)
    assert body["monitoring_interval_minutes"] == 0
    text = json.dumps(body).lower()
    assert not any(word in text for word in ("key_hash", "hashed_password", "cdrk_", "secret_key", "mfa_secret"))   # words of advice may say "password"; stored secrets must never appear


# ------------------------------------------------------------------ the background monitor
def test_the_background_monitor_is_off_by_default():
    assert settings.MONITOR_INTERVAL_MINUTES == 0

    async def go():
        async with monitor_loop.monitoring_lifespan(None):
            return [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]

    assert asyncio.run(go()) == []


def test_when_on_it_runs_repeatedly_and_stops_cleanly(monkeypatch):
    calls = []
    monkeypatch.setattr(settings, "MONITOR_INTERVAL_MINUTES", 1)
    monkeypatch.setattr(monitor_loop, "FIRST_RUN_DELAY_SECONDS", 0.01)
    monkeypatch.setattr(monitor_loop, "SECONDS_PER_MINUTE", 0.02)
    monkeypatch.setattr(monitor_loop, "run_once", lambda: calls.append(1) or 0)

    async def go():
        async with monitor_loop.monitoring_lifespan(None):
            await asyncio.sleep(0.4)
        return [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]

    assert asyncio.run(go()) == [] and len(calls) >= 3


def test_a_run_that_fails_does_not_stop_the_monitor(monkeypatch):
    calls = []

    def sometimes_fails():
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("the database was briefly away")
        return 0

    monkeypatch.setattr(settings, "MONITOR_INTERVAL_MINUTES", 1)
    monkeypatch.setattr(monitor_loop, "FIRST_RUN_DELAY_SECONDS", 0.01)
    monkeypatch.setattr(monitor_loop, "SECONDS_PER_MINUTE", 0.02)
    monkeypatch.setattr(monitor_loop, "run_once", sometimes_fails)

    async def go():
        async with monitor_loop.monitoring_lifespan(None):
            await asyncio.sleep(0.4)

    asyncio.run(go())
    assert len(calls) >= 3


def test_backups_can_be_left_out_of_the_monitoring_for_an_environment_that_has_none(db_session, monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")        # in production a missing backup is urgent ...
    assert next(c for c in m.run_checks(db_session) if c.key == "backup").status == "CRITICAL"
    monkeypatch.setattr(settings, "BACKUP_MONITORING", False)         # ... unless this environment (staging) has no backup task
    check = next(c for c in m.run_checks(db_session) if c.key == "backup")
    assert check.status == "INFO" and "not monitored" in check.message
