"""
MODULE: System monitoring.

Nine small checks that answer "is the system healthy, and is anyone attacking it?": the database, its schema version, the backups, the
disk, failed sign-ins, refused API keys, locked accounts, API keys about to expire, and whether more than one administrator exists.
Each check is its own function with its inputs spelled out, so it can be tested alone, and a check that itself fails is reported as a
warning ("could not be checked") instead of breaking the page.

The result is shown on the System Status page (System Administrator only), printed by scripts/system_check.py for the host's own
monitoring, and turned into in-application notifications for the System Administrators by notify_admins (no e-mail or SMS exists here).
A repeated alert is not repeated: an urgent one is told again after a day, an attention one after a week, and a change of severity at once.
"""
import json
import logging
import shutil
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import distinct, func, inspect as sa_inspect, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.startup_checks import is_production
from app.core.timeutil import utcnow
from app.models.models import ApiClient, AuditLog, Notification, RoleEnum, User

logger = logging.getLogger("cdr.monitor")

OK, INFO, WARN, CRITICAL = "OK", "INFO", "WARN", "CRITICAL"
_SEVERITY = {INFO: 0, OK: 0, WARN: 1, CRITICAL: 2}
ALERT_REPEAT_AFTER = {CRITICAL: timedelta(hours=24), WARN: timedelta(days=7)}
BACKEND_DIR = Path(__file__).resolve().parents[2]
KEY_EXPIRY_WARNING_DAYS = 14
KEY_RECENTLY_EXPIRED_DAYS = 30
KEY_FAILURES_WARN, KEY_FAILURES_CRITICAL = 20, 100       # refused API-key requests in the last hour
LOCKOUTS_WARN, LOCKOUTS_CRITICAL = 2, 5                  # accounts locked in the last hour
LOCKED_NOW_WARN = 3


@dataclass
class Check:
    key: str
    title: str
    status: str
    message: str
    details: dict = field(default_factory=dict)


def overall(checks) -> str:
    worst = max((_SEVERITY[c.status] for c in checks), default=0)
    return {0: OK, 1: WARN, 2: CRITICAL}[worst]


def exit_code(checks) -> int:
    """For a scheduler or a monitoring tool on the host: 0 = all fine, 1 = something to look at, 2 = something is wrong."""
    return {OK: 0, WARN: 1, CRITICAL: 2}[overall(checks)]


def _names(names, limit=5) -> str:
    names = list(names)
    shown = ", ".join(names[:limit])
    return shown + (f" and {len(names) - limit} more" if len(names) > limit else "")


# ------------------------------------------------------------------ the database
def check_database(db: Session) -> Check:
    started = time.perf_counter()
    db.execute(text("SELECT 1"))
    ms = (time.perf_counter() - started) * 1000
    details = {"response_ms": round(ms, 1)}
    try:
        if db.get_bind().dialect.name == "postgresql":
            details["database_megabytes"] = round((db.execute(text("select pg_database_size(current_database())")).scalar() or 0) / 1_048_576, 1)
    except Exception:
        db.rollback()                      # the size is a nicety; never let it fail the check
    slow = ms > 500
    return Check("database", "Database", WARN if slow else OK, f"The database answers in {ms:.0f} ms." + (" That is slow." if slow else ""), details)


def current_revision(db: Session):
    return db.execute(text("select version_num from alembic_version")).scalar()


def head_revision():
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    return ScriptDirectory.from_config(config).get_current_head()


def check_schema(db: Session) -> Check:
    title = "Database schema version"
    if not sa_inspect(db.get_bind()).has_table("alembic_version"):
        return Check("schema", title, INFO, "The schema version is not tracked here (the database was not built by the migrations).")
    current, head = current_revision(db), head_revision()
    details = {"database": current, "application": head}
    if current == head:
        return Check("schema", title, OK, f"The database schema is at the version this application expects ({current}).", details)
    return Check("schema", title, CRITICAL, f"The database schema ({current}) is not the version this application expects ({head}). Run the migrations (scripts/prod_up does it).", details)


# ------------------------------------------------------------------ the backups
def check_backup(status_dir, now: datetime, max_age_hours: float, production: bool) -> Check:
    """Reads what the backup task (scripts/prod_ops.py backup) left in the status folder. It cannot read the backups themselves."""
    title = "Backups"
    path = Path(status_dir) / "last_backup.json"
    if not path.is_file():
        if production:
            return Check("backup", title, CRITICAL, "No backup has been recorded. Run: python scripts/prod_ops.py backup, and schedule it (prod_ops.py schedule).")
        return Check("backup", title, INFO, "Backups are monitored in production only.")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        taken = datetime.strptime(data["taken_utc"], "%Y%m%dT%H%M%SZ")
    except Exception:
        return Check("backup", title, CRITICAL, "The backup status file cannot be read. Check the backup task and run: python scripts/prod_ops.py status.")
    age = max(0.0, (now - taken).total_seconds() / 3600)
    details = {
        "taken_utc": taken.isoformat(timespec="seconds") + "Z", "age_hours": round(age, 1), "limit_hours": max_age_hours,
        "result": data.get("result"), "schema_revision": data.get("revision"), "database_bytes": data.get("database_bytes"),
        "uploads_bytes": data.get("uploads_bytes"), "off_machine_copy": bool(data.get("off_machine")),
    }
    if age > max_age_hours:
        return Check("backup", title, CRITICAL, f"The newest backup is {age:.0f} hours old (limit {max_age_hours:g}). The scheduled backup may not be running.", details)
    if data.get("result") != "OK":
        why = str(data.get("copy_error") or "see backup.log")[:200]
        return Check("backup", title, WARN, f"The newest backup was made, but copying it off the machine failed: {why}", details)
    if not data.get("off_machine"):
        return Check("backup", title, WARN, f"The newest backup is {age:.1f} hours old, but there is no off-machine copy: it would not survive the loss of this disk (prod_ops.py backup --copy-to).", details)
    return Check("backup", title, OK, f"The newest backup is {age:.1f} hours old and was copied off the machine.", details)


def check_disk(total: int, free: int, warn_percent: int, critical_percent: int) -> Check:
    percent = 100.0 * free / total if total else 0.0
    details = {"free_gigabytes": round(free / 1e9, 1), "total_gigabytes": round(total / 1e9, 1), "free_percent": round(percent, 1)}
    message = f"{percent:.0f}% of the disk is free ({free / 1e9:.1f} GB)."
    if percent < critical_percent:
        return Check("disk", "Disk space", CRITICAL, message + " Uploads and backups need room: free space now.", details)
    if percent < warn_percent:
        return Check("disk", "Disk space", WARN, message + " It is getting low.", details)
    return Check("disk", "Disk space", OK, message, details)


# ------------------------------------------------------------------ attacks and misuse
def _count(db: Session, actions, since: datetime) -> int:
    return db.query(func.count(AuditLog.id)).filter(AuditLog.action.in_(actions), AuditLog.created_at >= since).scalar() or 0


def check_signins(db: Session, now: datetime, warn: int, critical: int) -> Check:
    """Wrong passwords and wrong second-step codes against EXISTING accounts. (An unknown username is not recorded: the rate limit covers it.)"""
    actions = ("LOGIN_FAILED", "MFA_FAILED", "LOGIN_LOCKED")
    hour = now - timedelta(hours=1)
    failures = _count(db, actions, hour)
    lockouts = _count(db, ("LOGIN_LOCKED",), hour)
    accounts = db.query(func.count(distinct(AuditLog.entity_id))).filter(AuditLog.action.in_(actions), AuditLog.created_at >= hour).scalar() or 0
    day = _count(db, actions, now - timedelta(hours=24))
    details = {"failed_last_hour": failures, "accounts_targeted_last_hour": accounts, "accounts_locked_last_hour": lockouts, "failed_last_24_hours": day}
    message = f"{failures} failed sign-in attempt(s) in the last hour against {accounts} account(s); {lockouts} account(s) locked."
    if failures >= critical or lockouts >= LOCKOUTS_CRITICAL:
        return Check("signins", "Failed sign-ins", CRITICAL, message + " This looks like an attack on passwords. Review the audit log.", details)
    if failures >= warn or lockouts >= LOCKOUTS_WARN:
        return Check("signins", "Failed sign-ins", WARN, message + " More than usual: review the audit log.", details)
    return Check("signins", "Failed sign-ins", OK, message, details)


def check_key_failures(db: Session, now: datetime) -> Check:
    hour = now - timedelta(hours=1)
    rows = db.query(AuditLog.details_json).filter(AuditLog.action == "INTEGRATION_AUTH_FAILED", AuditLog.created_at >= hour).limit(1000).all()
    reasons = Counter((r[0] or {}).get("reason", "unknown") if isinstance(r[0], dict) else "unknown" for r in rows)
    total = sum(reasons.values())
    details = {"refused_last_hour": total, "by_reason": dict(reasons)}
    message = f"{total} API-key request(s) refused in the last hour."
    if total >= KEY_FAILURES_CRITICAL:
        return Check("key_failures", "Refused API keys", CRITICAL, message + " Someone is trying keys, or a system is using a revoked one.", details)
    if total >= KEY_FAILURES_WARN:
        return Check("key_failures", "Refused API keys", WARN, message + " Check which key and why (audit log, INTEGRATION_AUTH_FAILED).", details)
    return Check("key_failures", "Refused API keys", OK, message, details)


def check_locked_accounts(db: Session, now: datetime) -> Check:
    locked = db.query(func.count(User.id)).filter(User.locked_until.isnot(None), User.locked_until > now).scalar() or 0
    status = WARN if locked >= LOCKED_NOW_WARN else OK
    return Check("locked_accounts", "Locked accounts", status, f"{locked} account(s) are locked at the moment.", {"locked_now": locked})


# ------------------------------------------------------------------ operations
def check_keys(db: Session, now: datetime) -> Check:
    """A key that expires silently stops a feed or a reader. Say so before it happens, and after."""
    live = db.query(ApiClient).filter(ApiClient.revoked_at.is_(None))
    soon = live.filter(ApiClient.expires_at > now, ApiClient.expires_at <= now + timedelta(days=KEY_EXPIRY_WARNING_DAYS)).order_by(ApiClient.expires_at).all()
    gone = live.filter(ApiClient.expires_at <= now, ApiClient.expires_at >= now - timedelta(days=KEY_RECENTLY_EXPIRED_DAYS)).order_by(ApiClient.expires_at.desc()).all()
    details = {"expiring_within_days": KEY_EXPIRY_WARNING_DAYS, "expiring": [{"name": k.name, "expires": k.expires_at.date().isoformat()} for k in soon],
               "expired_recently": [{"name": k.name, "expired": k.expires_at.date().isoformat()} for k in gone]}
    parts = []
    if gone:
        parts.append(f"expired and now refused: {_names(k.name for k in gone)}")
    if soon:
        parts.append(f"expiring within {KEY_EXPIRY_WARNING_DAYS} days: {_names(k.name for k in soon)}")
    if parts:
        return Check("keys", "API keys", WARN, "Keys " + "; ".join(parts) + ". Create replacements before the system using them stops.", details)
    return Check("keys", "API keys", OK, "No API key is about to expire and none expired recently without being replaced.", details)


def check_administrators(db: Session) -> Check:
    active = db.query(func.count(User.id)).filter(User.role == RoleEnum.SYSTEM_ADMIN, User.is_active == True).scalar() or 0  # noqa: E712
    if active == 0:
        return Check("administrators", "Administrators", CRITICAL, "There is no active System Administrator.", {"active": active})
    if active == 1:
        return Check("administrators", "Administrators", WARN, "Only one System Administrator is active. If they lose their phone or password, nobody can reset them: create a second one.", {"active": active})
    return Check("administrators", "Administrators", OK, f"{active} System Administrators are active.", {"active": active})


# ------------------------------------------------------------------ all of them
def _safe(db: Session, key: str, title: str, run) -> Check:
    try:
        return run()
    except Exception as exc:          # a check that cannot run must not take the page down
        try:
            db.rollback()
        except Exception:
            pass
        logger.exception("Monitoring check %s failed", key)
        return Check(key, title, WARN, f"{title} could not be checked ({type(exc).__name__}). See the server log.")


def _disk() -> Check:
    path = Path(settings.UPLOAD_DIR)
    while not path.exists() and path != path.parent:
        path = path.parent
    usage = shutil.disk_usage(path)
    return check_disk(usage.total, usage.free, settings.ALERT_DISK_FREE_WARN_PERCENT, settings.ALERT_DISK_FREE_CRITICAL_PERCENT)


def run_checks(db: Session, now: datetime = None) -> list:
    now = now or utcnow()
    return [
        _safe(db, "database", "Database", lambda: check_database(db)),
        _safe(db, "schema", "Database schema version", lambda: check_schema(db)),
        _safe(db, "backup", "Backups", lambda: check_backup(settings.BACKUP_STATUS_DIR, now, settings.BACKUP_MAX_AGE_HOURS, is_production(settings.ENVIRONMENT))
              if settings.BACKUP_MONITORING else Check("backup", "Backups", INFO, "Backups are not monitored in this environment (BACKUP_MONITORING is off).")),
        _safe(db, "disk", "Disk space", _disk),
        _safe(db, "signins", "Failed sign-ins", lambda: check_signins(db, now, settings.ALERT_SIGNIN_FAILURES_WARN, settings.ALERT_SIGNIN_FAILURES_CRITICAL)),
        _safe(db, "key_failures", "Refused API keys", lambda: check_key_failures(db, now)),
        _safe(db, "locked_accounts", "Locked accounts", lambda: check_locked_accounts(db, now)),
        _safe(db, "keys", "API keys", lambda: check_keys(db, now)),
        _safe(db, "administrators", "Administrators", lambda: check_administrators(db)),
    ]


# ------------------------------------------------------------------ telling the administrators
def notify_admins(db: Session, checks, now: datetime = None) -> int:
    """One in-application notification per active System Administrator for each alert, repeated only after ALERT_REPEAT_AFTER (or if it gets worse)."""
    now = now or utcnow()
    admins = db.query(User).filter(User.role == RoleEnum.SYSTEM_ADMIN, User.is_active == True).all()  # noqa: E712
    created = 0
    for check in checks:
        if check.status not in ALERT_REPEAT_AFTER:
            continue
        marker = f"{check.key}:{check.status}"
        since = now - ALERT_REPEAT_AFTER[check.status]
        for admin in admins:
            told = db.query(Notification.id).filter(
                Notification.user_id == admin.id, Notification.type == "SYSTEM_ALERT", Notification.related_entity_type == "Alert",
                Notification.related_entity_id == marker, Notification.created_at >= since).first()
            if told:
                continue
            db.add(Notification(user_id=admin.id, type="SYSTEM_ALERT", message=f"[{check.status}] {check.title}: {check.message}"[:500],
                                related_entity_type="Alert", related_entity_id=marker))
            created += 1
    db.commit()
    return created
