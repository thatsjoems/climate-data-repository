#!/usr/bin/env python3
"""
Check the production configuration BEFORE anything is started. Nothing is changed.

    python scripts/check_production_config.py [--env-file .env.production] [--no-certs]

Needs only Python 3 (no extra packages). Checks the secrets (strong, not placeholders), the domain, the TLS certificate files, and that the
production Compose file and web-server configuration keep their safety properties (database and backend
not published, HTTPS, separate volumes, nothing ignored by git that must be). Exit code 0 means OK.
"""
import argparse
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SAFE = re.compile(r"^[A-Za-z0-9]+$")
PLACEHOLDER = ("set-by-prod_setup", "change", "cdr_dev_only", "password", "secret-key")


def parse_env(path: pathlib.Path) -> dict:
    env = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


def weak(value: str) -> bool:
    return any(p in value.lower() for p in PLACEHOLDER)


def check_env(env: dict, check_certs: bool) -> list:
    problems = []
    domain = env.get("CDR_DOMAIN", "")
    if not domain or "://" in domain or "/" in domain or " " in domain or "example" in domain.lower():
        problems.append("CDR_DOMAIN must be the real address users type, without https:// (not the example).")
    key = env.get("SECRET_KEY", "")
    if len(key) < 32 or weak(key):
        problems.append("SECRET_KEY must be at least 32 random characters and not a placeholder (run scripts/prod_setup.py).")
    pg, app = env.get("POSTGRES_PASSWORD", ""), env.get("APP_DB_PASSWORD", "")
    for name, value in (("POSTGRES_PASSWORD", pg), ("APP_DB_PASSWORD", app)):
        if len(value) < 24 or weak(value) or not SAFE.match(value):
            problems.append(f"{name} must be at least 24 letters and digits only (so it is safe in a URL and a SQL script), not a placeholder.")
    if pg and pg == app:
        problems.append("APP_DB_PASSWORD must differ from POSTGRES_PASSWORD.")
    url = env.get("BACKEND_DATABASE_URL", "")
    m = re.match(r"^postgresql://([^:]+):([^@]+)@db:5432/climate_data_repository$", url)
    if not m:
        problems.append("BACKEND_DATABASE_URL must look like postgresql://<user>:<password>@db:5432/climate_data_repository.")
    elif m.group(2) not in (pg, app):
        problems.append("BACKEND_DATABASE_URL carries a password that is neither POSTGRES_PASSWORD nor APP_DB_PASSWORD.")
    if check_certs:
        cert_dir = pathlib.Path(env.get("CERT_DIR", "./certs"))
        cert_dir = cert_dir if cert_dir.is_absolute() else ROOT / cert_dir
        for f in ("fullchain.pem", "privkey.pem"):
            if not (cert_dir / f).is_file():
                problems.append(f"TLS certificate file missing: {cert_dir / f}")
    return problems


def compose_facts(text: str) -> dict:
    """Read the few facts we check straight from the text of docker-compose.prod.yml (no YAML library needed)."""
    facts = {"name": None, "services": {}, "volumes": []}
    top = service = None
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip())
        stripped = line.strip()
        if indent == 0:
            top = stripped.rstrip(":").split(":")[0]
            service = None
            if stripped.startswith("name:"):
                facts["name"] = stripped.split(":", 1)[1].strip()
            continue
        if top == "services":
            if indent == 2 and stripped.endswith(":"):
                service = stripped[:-1]
                facts["services"][service] = {"ports": [], "env": {}, "has_ports": False}
            elif service and indent == 4 and stripped == "ports:":
                facts["services"][service]["has_ports"] = True
            elif service and facts["services"][service]["has_ports"] and indent == 6 and stripped.startswith("- "):
                facts["services"][service]["ports"].append(stripped[2:].strip().strip('"\''))
            elif service and indent == 6 and ":" in stripped and not stripped.startswith("-"):
                k, v = stripped.split(":", 1)
                facts["services"][service]["env"][k.strip()] = v.strip().strip('"\'')
        elif top == "volumes" and indent == 2 and stripped.endswith(":"):
            facts["volumes"].append(stripped[:-1])
    return facts


def check_files() -> list:
    problems = []
    facts = compose_facts((ROOT / "docker-compose.prod.yml").read_text(encoding="utf-8"))
    services = facts["services"]
    if facts["name"] != "cdr-prod":
        problems.append("docker-compose.prod.yml must keep its own project name (cdr-prod), so it never mixes with a development stack.")
    for s in ("db", "backend", "frontend"):
        if s not in services:
            problems.append(f"service {s} is missing from docker-compose.prod.yml")
    for s in ("db", "backend"):
        if services.get(s, {}).get("has_ports"):
            problems.append(f"{s} must not publish any port in production.")
    if services.get("backend", {}).get("env", {}).get("ENVIRONMENT") != "production":
        problems.append("backend must run with ENVIRONMENT=production.")
    if not services.get("backend", {}).get("env", {}).get("MFA_REQUIRED"):
        problems.append("backend must set MFA_REQUIRED (two-step sign-in for the Bank's staff).")
    if not services.get("backend", {}).get("env", {}).get("MONITOR_INTERVAL_MINUTES") or ":/backup-status:ro" not in (ROOT / "docker-compose.prod.yml").read_text(encoding="utf-8"):
        problems.append("backend must set MONITOR_INTERVAL_MINUTES and mount ./backups/status at /backup-status read-only (monitoring and backup alerts).")
    if not services.get("backend", {}).get("env", {}).get("TRUSTED_PROXIES"):
        problems.append("backend must set TRUSTED_PROXIES (the proxy in front of it), or every rate limit sees only the proxy address.")
    if not any(p.endswith(":443") for p in services.get("frontend", {}).get("ports", [])):
        problems.append("frontend must publish 443 (HTTPS).")
    compose_text = (ROOT / "docker-compose.prod.yml").read_text(encoding="utf-8")
    for s in ("backend", "frontend"):                         # container hardening (docs/DOCKER.md)
        m = re.search(rf"\n  {s}:\n(.*?)(?=\n  [a-z]+:\n|\nvolumes:)", compose_text, re.S)
        section = m.group(1) if m else ""
        if "no-new-privileges" not in section or "cap_drop" not in section or "- ALL" not in section:
            problems.append(f"service {s} in docker-compose.prod.yml must keep no-new-privileges and cap_drop: ALL (container hardening).")
    for v in facts["volumes"]:
        if v in ("cdr_postgres_data", "cdr_uploads"):
            problems.append(f"volume {v} is the development volume: production must use its own (cdr_prod_*).")
    nginx = (ROOT / "frontend" / "nginx.prod.conf").read_text(encoding="utf-8")
    for needle in ("ssl_certificate ", "TLSv1.3", "Strict-Transport-Security", "return 301 https://", "client_max_body_size 25M", "proxy_pass http://backend:8000/api/", "proxy_read_timeout 300s", "add_header Content-Security-Policy", "proxy_hide_header Strict-Transport-Security"):
        if needle not in nginx:
            problems.append(f"frontend/nginx.prod.conf lacks: {needle.strip()}")
    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    for needle in (".env.production", "certs/", ".env.staging", "certs-staging/"):
        if needle not in ignore:
            problems.append(f".gitignore must contain {needle}")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--env-file", default=".env.production")
    ap.add_argument("--no-certs", action="store_true", help="skip the certificate check (for example when run in a container)")
    args = ap.parse_args()
    env_path = pathlib.Path(args.env_file)
    env_path = env_path if env_path.is_absolute() else ROOT / env_path
    if not env_path.is_file():
        print(f"{env_path.name} not found. Run: python scripts/prod_setup.py --domain <address>")
        return 2
    env = parse_env(env_path)
    problems = check_env(env, not args.no_certs) + check_files()
    if env_path.name == ".env.production":
        if env.get("RATE_LIMIT_ENABLED", "true").strip().lower() in ("false", "0", "no", "off"):
            problems.append("RATE_LIMIT_ENABLED must not be switched off in .env.production (only staging may, for load tests).")
        if env.get("CDR_ALLOW_LOAD_TEST", "").strip():
            problems.append("CDR_ALLOW_LOAD_TEST must not be set in .env.production: the load-test tool must never run against production.")
    if problems:
        print("PRODUCTION CONFIGURATION: NOT READY")
        for p in problems:
            print("  -", p)
        return 1
    print("PRODUCTION CONFIGURATION: OK" + ("" if not args.no_certs else " (certificate files not checked)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
