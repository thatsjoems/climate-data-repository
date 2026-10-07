"""
Create the first System Administrator (see app/services/admin_bootstrap.py for why this exists).

Run inside the backend container, in a terminal (do not add -T to docker compose exec):

    docker compose exec backend python scripts/create_admin.py \
        --username <name> --full-name "<Full Name>" --email <address>

The password is typed at a hidden prompt (twice) - it is deliberately NOT a command-line option,
so it never lands in shell history or the process list.

    --must-change-password   force a password change at the first sign-in
    --allow-additional       recovery only: create one even though an active administrator exists
"""
import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.database import SessionLocal  # noqa: E402
from app.services.admin_bootstrap import BootstrapError, create_first_admin  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Create the first System Administrator.")
    parser.add_argument("--username", required=True)
    parser.add_argument("--full-name", required=True)
    parser.add_argument("--email", required=True)
    parser.add_argument("--must-change-password", action="store_true")
    parser.add_argument("--allow-additional", action="store_true")
    args = parser.parse_args()

    if not sys.stdin.isatty():
        print("This needs an interactive terminal to ask for the password. Run it with "
              "'docker compose exec backend ...' without the -T flag.", file=sys.stderr)
        return 2

    password = getpass.getpass("Password: ")
    if password != getpass.getpass("Repeat password: "):
        print("Not created: the two passwords do not match.", file=sys.stderr)
        return 1

    db = SessionLocal()
    try:
        user = create_first_admin(
            db,
            full_name=args.full_name,
            username=args.username,
            email=args.email,
            password=password,
            allow_additional=args.allow_additional,
            must_change_password=args.must_change_password,
        )
        created_username = user.username  # read while the session is still open (a closed session cannot load it)
    except BootstrapError as exc:
        print(f"Not created: {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()

    print(f"Created System Administrator '{created_username}'. You can now sign in to the web application.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
