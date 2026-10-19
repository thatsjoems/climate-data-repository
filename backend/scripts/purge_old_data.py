#!/usr/bin/env python3
"""
Removes expired refresh tokens and old notifications. By default it only COUNTS (a dry run); add --apply to delete.

    docker compose exec backend python scripts/purge_old_data.py            (dry run)
    docker compose exec backend python scripts/purge_old_data.py --apply
    from the host:  python scripts/prod_ops.py purge [--apply]

Deletes with the OWNER database role (MIGRATION_DATABASE_URL): the application's own role has no DELETE right, on purpose, and keeps none.
Audit logs, submissions and climate data are never touched. A run that deletes something writes one audit entry (DATA_PURGE).
"""
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine                  # noqa: E402
from sqlalchemy.orm import sessionmaker               # noqa: E402

from app.core.config import settings                  # noqa: E402
from app.core.timeutil import utcnow                  # noqa: E402
from app.services.audit_service import record_audit   # noqa: E402
from app.services.retention_service import (          # noqa: E402
    ANY_NOTIFICATION_DAYS, READ_NOTIFICATION_DAYS, TOKEN_GRACE_DAYS, purge_old_data)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="really delete (without it, only count)")
    args = ap.parse_args()
    url = os.environ.get("MIGRATION_DATABASE_URL") or settings.DATABASE_URL
    engine = create_engine(url, connect_args={"check_same_thread": False} if url.startswith("sqlite") else {})
    db = sessionmaker(bind=engine)()
    try:
        r = purge_old_data(db, utcnow(), apply=args.apply)
        if args.apply and r.total:
            record_audit(db, None, "DATA_PURGE", None, None,
                         f"Housekeeping from the command line: {r.refresh_tokens} refresh token(s), {r.notifications} notification(s) removed",
                         commit=False)
        db.commit()
    finally:
        db.close()
    verb = "Removed" if args.apply else "Would remove (dry run; add --apply to delete)"
    print(f"{verb}: {r.refresh_tokens} refresh token(s) expired or revoked over {TOKEN_GRACE_DAYS} days ago; "
          f"{r.notifications} notification(s) (read over {READ_NOTIFICATION_DAYS} days old, or any over {ANY_NOTIFICATION_DAYS} days old).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
