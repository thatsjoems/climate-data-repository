"""
Housekeeping of old refresh tokens and notifications (app/services/retention_service.py, scripts/purge_old_data.py).

What matters: recent and still-useful rows are never touched, the dry run deletes nothing, and nothing else (audit logs above all) is removed.
"""
import importlib.util
from datetime import timedelta
from pathlib import Path

from app.core.timeutil import utcnow
from app.models.models import AuditLog, Notification, RefreshToken
from app.services.retention_service import purge_old_data
from tests.conftest import make_user

BACKEND = Path(__file__).resolve().parent.parent


def _token(db, user, n, expires_days_ago=None, revoked_days_ago=None, expires_in_days=None):
    now = utcnow()
    expires = now - timedelta(days=expires_days_ago) if expires_days_ago is not None else now + timedelta(days=expires_in_days or 7)
    db.add(RefreshToken(user_id=user.id, token_hash=f"{n:064d}", created_at=now - timedelta(days=400), expires_at=expires,
                        revoked_at=now - timedelta(days=revoked_days_ago) if revoked_days_ago is not None else None))
    db.commit()


def _note(db, user, age_days, read):
    db.add(Notification(user_id=user.id, message="x", is_read=read, created_at=utcnow() - timedelta(days=age_days)))
    db.commit()


def test_dry_run_counts_but_deletes_nothing(db_session):
    u = make_user(db_session)
    _token(db_session, u, 1, expires_days_ago=60)
    _note(db_session, u, 200, read=True)
    r = purge_old_data(db_session, utcnow(), apply=False)
    assert (r.refresh_tokens, r.notifications, r.applied) == (1, 1, False)
    assert db_session.query(RefreshToken).count() == 1 and db_session.query(Notification).count() == 1


def test_old_tokens_go_and_recent_or_live_ones_stay(db_session):
    u = make_user(db_session)
    _token(db_session, u, 1, expires_days_ago=60)          # expired long ago: goes
    _token(db_session, u, 2, expires_days_ago=5)           # expired recently: kept (reuse of a rotated token must stay detectable)
    _token(db_session, u, 3, expires_in_days=7, revoked_days_ago=60)   # revoked long ago: goes
    _token(db_session, u, 4, expires_in_days=7, revoked_days_ago=2)    # revoked just now: kept
    _token(db_session, u, 5, expires_in_days=7)            # live: kept
    r = purge_old_data(db_session, utcnow(), apply=True)
    db_session.commit()
    assert r.refresh_tokens == 2
    assert sorted(t.token_hash[-1] for t in db_session.query(RefreshToken)) == ["2", "4", "5"]


def test_notifications_read_after_90_days_or_any_after_a_year(db_session):
    u = make_user(db_session)
    _note(db_session, u, 100, read=True)     # goes
    _note(db_session, u, 100, read=False)    # unread and not a year old: kept
    _note(db_session, u, 30, read=True)      # recent: kept
    _note(db_session, u, 400, read=False)    # a year old, even unread: goes
    r = purge_old_data(db_session, utcnow(), apply=True)
    db_session.commit()
    assert r.notifications == 2 and db_session.query(Notification).count() == 2


def test_audit_logs_are_never_touched(db_session):
    u = make_user(db_session)
    db_session.add(AuditLog(user_id=u.id, action="LOGIN", created_at=utcnow() - timedelta(days=2000)))
    db_session.commit()
    purge_old_data(db_session, utcnow(), apply=True)
    db_session.commit()
    assert db_session.query(AuditLog).count() == 1


def test_the_script_is_dry_by_default_and_names_the_owner_role():
    spec = importlib.util.spec_from_file_location("purge_tool", BACKEND / "scripts" / "purge_old_data.py")
    text = (BACKEND / "scripts" / "purge_old_data.py").read_text(encoding="utf-8")
    assert spec is not None
    assert 'action="store_true"' in text and "MIGRATION_DATABASE_URL" in text and "DATA_PURGE" in text
