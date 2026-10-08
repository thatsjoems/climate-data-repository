#!/usr/bin/env python3
"""
The checks of the System Status page, from the server, for the host's own scheduler or monitoring tool.

    docker compose exec backend python scripts/system_check.py        (or, from the host:  python scripts/prod_ops.py check)

Exit code 0 = everything fine, 1 = something to look at (attention), 2 = something is wrong (urgent).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.database import SessionLocal            # noqa: E402
from app.services import monitoring_service as monitoring   # noqa: E402


def main() -> int:
    db = SessionLocal()
    try:
        checks = monitoring.run_checks(db)
    finally:
        db.close()
    print(f"SYSTEM CHECK ({monitoring.utcnow().strftime('%Y-%m-%d %H:%M')} UTC): {monitoring.overall(checks)}")
    for c in checks:
        print(f"  [{c.status:<8}] {c.title}: {c.message}")
    return monitoring.exit_code(checks)


if __name__ == "__main__":
    sys.exit(main())
