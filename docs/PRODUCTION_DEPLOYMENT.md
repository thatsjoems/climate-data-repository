# Production deployment

The production stack is **separate from the development stack**: its own Compose file
(`docker-compose.prod.yml`), its own project name (`cdr-prod`) and its own data volumes
(`cdr_prod_postgres_data`, `cdr_prod_uploads`). It can run on the same machine as a development stack
without touching its data. `docker-compose.yml` is unchanged.

## What is different from development

| | Development | Production |
|---|---|---|
| Open ports | 5173, 8000, 127.0.0.1:5433 | **80 and 443 only** (the database and the backend are not published) |
| Encryption | none | **HTTPS** (TLS 1.2 and 1.3), HTTP redirected, HSTS |
| Accounts | four demonstration accounts | **none**; the first administrator is created with a command |
| API documentation | `/docs` | **not served** |
| Secrets | defaults in the Compose file | random, in `.env.production` (never in git) |
| Database user | superuser `postgres` | restricted role `cdr_app` (no delete, no schema change, audit tables append-only) |
| Backend refuses to start | with a weak key | with a weak key **or** the shipped database password |
| Logs | unlimited | rotated (10 MB x 5 per service) |
| Health checks | database | database, backend, web server; start order follows health |

## Steps

1. **Prepare the server**: Docker with Compose v2, ports 80 and 443 free, DNS pointing the address at the server.
2. **Create the settings** (once): `python scripts/prod_setup.py --domain <address>`
   (without Python: `docker run --rm -v "${PWD}:/work" -w /work python:3.12-slim python scripts/prod_setup.py --domain <address>`).
   This writes `.env.production` with random secrets and prints nothing secret. It refuses to overwrite an existing file.
3. **Put the certificate** in `./certs`: `fullchain.pem` and `privkey.pem` (from BOT ICT). For a trial only, a self-signed one:
   `openssl req -x509 -nodes -newkey rsa:2048 -days 30 -keyout certs/privkey.pem -out certs/fullchain.pem -subj "/CN=<address>" -addext "subjectAltName=DNS:<address>"`.
   Without OpenSSL installed (Windows), use Docker instead:
   `docker run --rm -v "${PWD}/certs:/certs" alpine/openssl req -x509 -nodes -newkey rsa:2048 -days 30 -keyout /certs/privkey.pem -out /certs/fullchain.pem -subj "/CN=localhost" -addext "subjectAltName=DNS:localhost"`
   (the browser will warn that a self-signed certificate is not trusted: expected for a trial).
   If ports 80 or 443 are already in use on the machine, set `HTTP_PORT` and `HTTPS_PORT` (for example 8080 and 8443) in `.env.production` and open `https://<address>:8443` directly.
4. **Check** (changes nothing): `python scripts/check_production_config.py`
5. **Start**: `.\scripts\prod_up.ps1` (Windows) or `./scripts/prod_up.sh` (Linux). It starts the database and backend, creates the
   restricted role, switches the backend to it, then starts the web server, waiting for each to be healthy. Safe to re-run.
6. **Create the first administrator**:
   `docker compose -f docker-compose.prod.yml --env-file .env.production exec backend python scripts/create_admin.py --username <name> --full-name "<Full Name>" --email <address>`
7. **Verify**: open `https://<address>`, sign in, then run
   `docker compose -f docker-compose.prod.yml --env-file .env.production exec backend python scripts/verify_db_constraints.py`
   (expect all protections present) and check that `http://<address>` redirects to HTTPS and `https://<address>/docs` is not an API page.

Shorthand for later commands: `$c = '-f','docker-compose.prod.yml','--env-file','.env.production'` then `docker compose @c ps` (PowerShell),
or `export COMPOSE_FILE=docker-compose.prod.yml COMPOSE_ENV_FILES=.env.production` (bash).

## Rate limits and the real client address

Behind the web server every connection reaches the backend from the web server's address. If the backend used that address, all users would share one sign-in allowance (10 a minute: one person trying passwords could stop everybody else signing in), and the audit log and the address list of an API key would see only the proxy.

The backend therefore reads the real caller from `X-Forwarded-For`, but **only** for connections that come from a trusted proxy (`TRUSTED_PROXIES`, comma-separated networks), and only the part the proxies added: the list is read from the right, skipping proxies of ours, so an address a caller writes to deceive the system is never reached. The production Compose file trusts the private networks, which is right because the web server is the only way in (the backend publishes no port). Change `TRUSTED_PROXIES` in `.env.production` only if another proxy or load balancer sits in front of the web server: put that proxy's network there. A mistake in the value stops the backend at start-up; leaving it empty in production logs a warning.

On a single Windows machine with Docker Desktop, requests from the browser reach the stack through Docker's own gateway (a private address), so every caller still looks like the gateway; the per-caller limit becomes visible on a real server where callers arrive from their own addresses.

## Windows: "the script is not digitally signed"

PowerShell may refuse the `.ps1` scripts (`backup.ps1`, `restore.ps1`, `prod_up.ps1`) because the project came from a download or a
synced folder. Either mark them as trusted once:

    Unblock-File .\scripts\*.ps1

or run one script without changing any setting of the machine:

    powershell -ExecutionPolicy Bypass -File .\scripts\backup.ps1

The second form affects only that command. The `.sh` scripts and the Python scripts are not affected.

## Updating and stopping

- Update: replace the project files, then `docker compose @c up -d --build`. Migrations run at start and never delete data. After an update that adds tables, run `prod_up` again: it re-applies the restricted-role grants to the new tables (safe to re-run).
- Stop: `docker compose @c down`. **Never `down -v`** on a system that holds real data: it deletes the database and the uploads.
- Backup, restore drill, restore and scheduling: `python scripts/prod_ops.py` (see BACKUP_AND_RECOVERY.md). **Take a backup before every update and rehearse a restore with `drill`.**

## Roll back

Stop the stack (`down`, without `-v`), restore the project files of the previous version, restore the last backup if a migration
was applied, and start again. Nothing in this procedure touches a development stack.

## Honest status

Verified here: the Compose file and nginx configuration parse and keep their safety properties; the settings generator and the
configuration checker behave as described, including on deliberately wrong settings; the development files are unchanged; the
backend change compiles. **Not verified here (no Docker in the authoring environment):** the real start of this stack, the TLS
handshake, the staged role switch, and PowerShell `prod_up.ps1`. Run steps 1 to 7 on a machine with Docker before relying on it.

## Not part of this document yet

Monitoring and alerts, multi-factor authentication, and the connectors that bring data in from TMA and PMO or call BSIS and RTIS are separate pieces
of work. (Scheduled backups with a restore drill, the real client address behind the proxy and keys for external systems are done: see
BACKUP_AND_RECOVERY.md, the section above and INTEGRATION_ACCESS.md.)
