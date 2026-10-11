"""
The two sign-in doors of the repository.

* internal - the Bank's own staff: BOT analysts and System Administrators (page /staff/login).
* external - the reporting institutions (page /login).

A sign-in page tells the server which door it is. A person whose role belongs to the other door is turned away after the
password has been proved (so nobody can learn which usernames exist), is told where to sign in, and the attempt is audited.
A caller that names no door (older scripts, tools) is not restricted here; the roles themselves still decide what anyone may do.
"""
from app.models.models import RoleEnum

INTERNAL = "internal"
EXTERNAL = "external"

_STAFF = (RoleEnum.BOT_USER, RoleEnum.SYSTEM_ADMIN)


def portal_of(role: RoleEnum) -> str:
    return INTERNAL if role in _STAFF else EXTERNAL


def wrong_portal_message(role: RoleEnum) -> str:
    """What to tell someone (who has already proved their password) who used the other door."""
    if portal_of(role) == INTERNAL:
        return "This sign-in page is for reporting institutions. Bank of Tanzania staff sign in at /staff/login."
    return "This sign-in page is for Bank of Tanzania staff only. Institution users sign in at /login."
