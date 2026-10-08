#!/usr/bin/env python3
"""
Create .env.production (or, with --stack staging, .env.staging) from .env.production.example with strong random secrets.

    python scripts/prod_setup.py --domain cdr.bot.go.tz
    python scripts/prod_setup.py --stack staging            (a rehearsal copy on this machine; see docs/STAGING.md)

Works on any machine with Python 3, or without Python installed:
    docker run --rm -v "${PWD}:/work" -w /work python:3.12-slim python scripts/prod_setup.py --domain <address>

It never overwrites an existing environment file unless --force is given (that would change the
database password of a database that already exists).

Staging uses its own secrets, its own certificate folder (certs-staging), ports 8080 and 8443 reachable only from this machine, no backup
monitoring and no two-step sign-in (so that it can be load-tested). It never shares a password, a volume or a port with production.
"""
import argparse
import pathlib
import re
import secrets
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOMAIN = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?$")
STAGING_VALUES = {"HTTP_PORT": "127.0.0.1:8080", "HTTPS_PORT": "127.0.0.1:8443", "CERT_DIR": "./certs-staging"}
STAGING_EXTRA = (
    "\n# --- staging only (written by scripts/prod_setup.py --stack staging) ---\n"
    "BACKUP_STATUS_HOST_DIR=./backups/staging-status\n"
    "BACKUP_MONITORING=false\n"
    "# Off so that load tests can sign in with a password alone. Set to true to rehearse the two-step sign-in (docs/MFA.md).\n"
    "MFA_REQUIRED=false\n"
    "# Staging only, for the load-test tool (docs/LOAD_TESTING.md): without the rate limit a load test would measure the limit, not the system,\n"
    "# and the tool refuses to run anywhere that does not say yes. The production checker refuses both lines in .env.production.\n"
    "RATE_LIMIT_ENABLED=false\n"
    "CDR_ALLOW_LOAD_TEST=yes\n"
)


def make_trial_certificate(cert_dir: pathlib.Path, domain: str) -> bool:
    """A throw-away self-signed certificate (30 days) for staging. Uses OpenSSL if installed, otherwise Docker. Returns False if neither is available."""
    cert_dir.mkdir(parents=True, exist_ok=True)
    subject = ["-subj", f"/CN={domain}", "-addext", f"subjectAltName=DNS:{domain},DNS:localhost,IP:127.0.0.1"]
    req = ["req", "-x509", "-nodes", "-newkey", "rsa:2048", "-days", "30"]
    try:
        if shutil.which("openssl"):
            cmd = ["openssl", *req, "-keyout", str(cert_dir / "privkey.pem"), "-out", str(cert_dir / "fullchain.pem"), *subject]
        elif shutil.which("docker"):
            cmd = ["docker", "run", "--rm", "-v", f"{cert_dir}:/certs", "alpine/openssl", *req, "-keyout", "/certs/privkey.pem", "-out", "/certs/fullchain.pem", *subject]
        else:
            return False
        subprocess.run(cmd, check=True, capture_output=True)
    except (subprocess.CalledProcessError, OSError):
        return False
    return (cert_dir / "fullchain.pem").is_file() and (cert_dir / "privkey.pem").is_file()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stack", choices=("production", "staging"), default="production")
    ap.add_argument("--domain", help="the address users will type, without https:// (required for production; staging uses localhost)")
    ap.add_argument("--cert-dir", help="folder with fullchain.pem and privkey.pem (production: ./certs)")
    ap.add_argument("--force", action="store_true", help="overwrite an existing environment file (new secrets!)")
    args = ap.parse_args()
    staging = args.stack == "staging"
    domain = args.domain or ("localhost" if staging else None)
    if not domain:
        ap.error("--domain is required for production")

    if not DOMAIN.match(domain) or "://" in domain or "example" in domain.lower():
        print("The domain must be the real address (letters, digits, dots, hyphens), without https:// and not an example.")
        return 2
    target = ROOT / (".env.staging" if staging else ".env.production")
    if target.exists() and not args.force:
        print(f"{target.name} already exists. Not overwritten: a new database password would not match an existing database.")
        print("Use --force only for a brand-new installation.")
        return 1

    user = "postgres"
    pg_password, app_password, secret_key = secrets.token_hex(20), secrets.token_hex(20), secrets.token_hex(32)
    cert_dir = args.cert_dir or ("./certs-staging" if staging else "./certs")
    values = {
        "CDR_DOMAIN": domain, "CERT_DIR": cert_dir, "POSTGRES_USER": user, "POSTGRES_PASSWORD": pg_password,
        "APP_DB_PASSWORD": app_password, "SECRET_KEY": secret_key,
        "BACKEND_DATABASE_URL": f"postgresql://{user}:{pg_password}@db:5432/climate_data_repository",
    }
    if staging:
        values.update({k: v for k, v in STAGING_VALUES.items() if k != "CERT_DIR"})
    text = (ROOT / ".env.production.example").read_text(encoding="utf-8")
    for key, value in values.items():
        text, n = re.subn(rf"^{key}=.*$", lambda _m, k=key, v=value: f"{k}={v}", text, flags=re.M)
        if n != 1:
            print(f"Could not set {key}: the example file is not as expected.")
            return 3
    if staging:
        text += STAGING_EXTRA
    target.write_text(text, encoding="utf-8", newline="\n")
    try:
        target.chmod(0o600)
    except OSError:
        pass
    certs = ROOT / ("certs-staging" if staging else "certs")
    certs.mkdir(exist_ok=True)
    (certs / "README.txt").write_text("Put the TLS certificate here:\n  fullchain.pem  (certificate and chain)\n  privkey.pem    (private key; keep it secret)\nThis folder is ignored by git.\n", encoding="utf-8")

    print(f"Created {target.name} for {domain} with new random secrets (not shown).")
    if staging:
        made = make_trial_certificate(certs, domain)
        print("A 30-day self-signed certificate was made in ./certs-staging (the browser will warn: expected)." if made else
              "No certificate was made (neither OpenSSL nor Docker was found): put fullchain.pem and privkey.pem in ./certs-staging.")
        print("Next:  scripts/staging_up.ps1 (or staging_up.sh)   then open https://localhost:8443   (see docs/STAGING.md)")
    else:
        print("Next:  1) put fullchain.pem and privkey.pem in ./certs   2) python scripts/check_production_config.py   3) scripts/prod_up.ps1 (or prod_up.sh)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
