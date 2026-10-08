#!/usr/bin/env python3
"""
Sets a new password for ONE person, from the server. For the case the web page cannot cover: an administrator who forgot their password and has no
other administrator to reset it for them.

    docker compose -f docker-compose.prod.yml --env-file .env.production exec backend python scripts/reset_password.py --username admin

The new password is typed at a hidden prompt (twice): it is deliberately NOT a command-line option, so it never lands in shell history or the process
list. It must meet the password policy. By default the person must choose their own password at the next sign-in (--no-forced-change turns that off).
The account is unlocked, every session it already had is ended, and the reset is audited as made from the command line. The two-step sign-in is left
as it is (scripts/reset_mfa.py removes it).
"""
import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.database import SessionLocal                                 # noqa: E402
from app.services.account_recovery import RecoveryError, reset_password    # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--username", required=True)
    ap.add_argument("--no-forced-change", action="store_true", help="do not require a new password at the next sign-in")
    args = ap.parse_args()
    password = getpass.getpass("New password: ")
    if password != getpass.getpass("Repeat the new password: "):
        print("Not changed: the two passwords do not match.", file=sys.stderr)
        return 1
    db = SessionLocal()
    try:
        user = reset_password(db, args.username, password, must_change=not args.no_forced_change)
        name, active = user.username, user.is_active
    except RecoveryError as exc:
        print(f"Not changed: {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()
    print(f"Password of '{name}' set." + ("" if args.no_forced_change else " They must choose a new one at their next sign-in."))
    if not active:
        print("Note: this account is deactivated and still cannot sign in.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
