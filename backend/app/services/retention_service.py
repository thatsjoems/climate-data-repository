"""
Housekeeping of data that only ever grows and is worthless once old: expired or revoked refresh tokens and old notifications.

NOT touched, on purpose: audit_logs (a retention period for the audit trail is the Bank's decision), submissions, loans, climate data.

Refresh tokens are kept for a grace period after they expire or are revoked, because a rotated token that shows up again is the sign of
a stolen copy (see the refresh endpoint); deleting it the same day would hide that signal.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.models.models import Notification, RefreshToken

TOKEN_GRACE_DAYS = 30
READ_NOTIFICATION_DAYS = 90
ANY_NOTIFICATION_DAYS = 365


@dataclass
class PurgeResult:
    refresh_tokens: int
    notifications: int
    applied: bool

    @property
    def total(self) -> int:
        return self.refresh_tokens + self.notifications


def _token_filter(now: datetime, grace_days: int):
    cutoff = now - timedelta(days=grace_days)
    return or_(RefreshToken.expires_at < cutoff, and_(RefreshToken.revoked_at.isnot(None), RefreshToken.revoked_at < cutoff))


def _notification_filter(now: datetime, read_days: int, any_days: int):
    return or_(
        and_(Notification.is_read.is_(True), Notification.created_at < now - timedelta(days=read_days)),
        Notification.created_at < now - timedelta(days=any_days),
    )


def purge_old_data(db: Session, now: datetime, apply: bool = False, token_grace_days: int = TOKEN_GRACE_DAYS,
                   read_notification_days: int = READ_NOTIFICATION_DAYS, any_notification_days: int = ANY_NOTIFICATION_DAYS) -> PurgeResult:
    """Counts what is old enough to go and, only when apply is True, deletes it. Commits nothing; the caller decides."""
    tokens = db.query(RefreshToken).filter(_token_filter(now, token_grace_days))
    notes = db.query(Notification).filter(_notification_filter(now, read_notification_days, any_notification_days))
    n_tokens, n_notes = tokens.count(), notes.count()
    if apply:
        tokens.delete(synchronize_session=False)
        notes.delete(synchronize_session=False)
    return PurgeResult(n_tokens, n_notes, apply)
