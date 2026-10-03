"""
Decides whether a user may authenticate (KG-02).

An institution user is usable only while BOTH the account itself and the
institution that owns it are active. Before this check existed, deactivating
an institution set a flag that nothing read: its users could still sign in,
refresh tokens and upload. The decision is centralised here so that login,
token refresh, per-request authentication and password recovery can never
disagree about it.

Kept free of framework imports so it can be unit-tested in isolation.
Semantics match the rest of the system: only an EXPLICIT `is_active is False`
on the institution blocks its users - a NULL in a legacy row is treated as
active, so an old database cannot lock a whole institution out by accident.
BOT Analysts and System Administrators have no institution and are never
affected by another organisation's status.
"""
from typing import Optional

ACCOUNT_DEACTIVATED = "account_deactivated"
INSTITUTION_DEACTIVATED = "institution_deactivated"


def authentication_block_reason(user) -> Optional[str]:
    """None if the user may authenticate; otherwise why not."""
    if not user.is_active:
        return ACCOUNT_DEACTIVATED
    institution = getattr(user, "institution", None)
    if institution is not None and institution.is_active is False:
        return INSTITUTION_DEACTIVATED
    return None
