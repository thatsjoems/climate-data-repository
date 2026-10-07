#!/usr/bin/env python3
"""
Create .env.production from .env.production.example with strong random secrets.

    python scripts/prod_setup.py --domain cdr.bot.go.tz

Works on any machine with Python 3, or without Python installed:
    docker run --rm -v "${PWD}:/work" -w /work python:3.12-slim python scripts/prod_setup.py --domain <address>

It never overwrites an existing .env.production unless --force is given (that would change the
database password of a database that already exists).
"""
import argparse
import pathlib
import re
import secrets
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOMAIN = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?$")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--domain", required=True, help="the address users will type, without https://")
    ap.add_argument("--cert-dir", default="./certs", help="folder with fullchain.pem and privkey.pem")
    ap.add_argument("--force", action="store_true", help="overwrite an existing .env.production (new secrets!)")
    args = ap.parse_args()

    if not DOMAIN.match(args.domain) or "://" in args.domain or "example" in args.domain.lower():
        print("The domain must be the real address (letters, digits, dots, hyphens), without https:// and not an example.")
        return 2
    target = ROOT / ".env.production"
    if target.exists() and not args.force:
        print(f"{target.name} already exists. Not overwritten: a new database password would not match an existing database.")
        print("Use --force only for a brand-new installation.")
        return 1

    user = "postgres"
    pg_password, app_password, secret_key = secrets.token_hex(20), secrets.token_hex(20), secrets.token_hex(32)
    values = {
        "CDR_DOMAIN": args.domain, "CERT_DIR": args.cert_dir, "POSTGRES_USER": user, "POSTGRES_PASSWORD": pg_password,
        "APP_DB_PASSWORD": app_password, "SECRET_KEY": secret_key,
        "BACKEND_DATABASE_URL": f"postgresql://{user}:{pg_password}@db:5432/climate_data_repository",
    }
    text = (ROOT / ".env.production.example").read_text(encoding="utf-8")
    for key, value in values.items():
        text, n = re.subn(rf"^{key}=.*$", lambda _m, k=key, v=value: f"{k}={v}", text, flags=re.M)
        if n != 1:
            print(f"Could not set {key}: the example file is not as expected.")
            return 3
    target.write_text(text, encoding="utf-8", newline="\n")
    try:
        target.chmod(0o600)
    except OSError:
        pass
    certs = ROOT / "certs"
    certs.mkdir(exist_ok=True)
    (certs / "README.txt").write_text("Put the TLS certificate here:\n  fullchain.pem  (certificate and chain)\n  privkey.pem    (private key; keep it secret)\nThis folder is ignored by git.\n", encoding="utf-8")

    print(f"Created {target.name} for {args.domain} with new random secrets (not shown).")
    print("Next:  1) put fullchain.pem and privkey.pem in ./certs   2) python scripts/check_production_config.py   3) scripts/prod_up.ps1 (or prod_up.sh)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
