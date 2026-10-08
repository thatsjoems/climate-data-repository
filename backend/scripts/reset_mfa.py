#!/usr/bin/env python3
"""
Removes the two-step sign-in of ONE person, from the server. For the case the web page cannot cover: an administrator who lost their
phone AND their recovery codes (an administrator cannot reset their own MFA through the application, on purpose).

    docker compose exec backend python scripts/reset_mfa.py --username <name>

The person enrols again at their next sign-in. The reset is audited as made from the command line. Needs access to the server, which is
the point: it is the Bank's own control, not something a web session can do.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.database import SessionLocal            # noqa: E402
from app.core.timeutil import utcnow                  # noqa: E402
from app.models.models import RefreshToken, User      # noqa: E402
from app.services.audit_service import record_audit   # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--username", required=True)
    args = ap.parse_args()
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == args.username).first()
        if user is None:
            print(f"No user named {args.username!r}.", file=sys.stderr)
            return 1
        user.mfa_enabled = False
        user.mfa_secret_encrypted = None
        user.mfa_recovery_hashes = None
        user.mfa_last_step = None
        user.mfa_enrolled_at = None
        db.query(RefreshToken).filter(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None)).update({"revoked_at": utcnow()})
        db.commit()
        record_audit(db, None, "MFA_RESET", "User", user.id, f"Two-step sign-in of {user.username} reset from the command line")
        name = user.username
    finally:
        db.close()
    print(f"Two-step sign-in of '{name}' removed. They will set it up again at their next sign-in.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
