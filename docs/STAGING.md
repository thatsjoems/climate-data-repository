# Staging: a rehearsal copy of production

Staging is a **second, separate copy of the production setup** on the same machine. It runs the same code and the same Compose file as
production, so what works there works in production: the start-up stages, the restricted database role, HTTPS, the migrations, the monitor.
Use it to **rehearse an upgrade** and to **load-test**, never to test on the real system.

## What keeps it apart from production
| | Production | Staging |
|---|---|---|
| Compose project (containers, network, data volumes) | `cdr-prod` | `cdr-staging` |
| Environment file | `.env.production` | `.env.staging` (its own random passwords and `SECRET_KEY`) |
| Address | `https://<domain>` (ports 80 and 443) | `https://localhost:8443` (or `https://127.0.0.1:8443`), reachable **only from this machine** |
| Certificate folder | `certs` | `certs-staging` (a 30-day self-signed certificate is made for you) |
| Two-step sign-in | required for staff | off by default, so a load test can sign in; set `MFA_REQUIRED=true` in `.env.staging` to rehearse it |
| Backup monitoring and backup task | yes | no (`BACKUP_MONITORING=false`); staging is disposable |
| Rate limits (sign-in 10 a minute, 200 requests a minute) | on | **off**, for load tests (`docs/LOAD_TESTING.md`); production's checker refuses it being off |
| Data | the real data | **empty, and only ever synthetic data** |

Nothing is shared: not a password, not a database, not an uploaded file, not a port. Both can run at the same time.

## Rule: no real data in staging
Staging has weaker safeguards than production on purpose (no backups, two-step sign-in off, a throw-away certificate). **Real data of the
Bank or of the reporting institutions must not be copied into it** without the Bank's written decision. This tool does not provide such a copy.
Use synthetic data (the load-test data of the next stage).

## Set up and start
```
python scripts/prod_setup.py --stack staging
powershell -ExecutionPolicy Bypass -File .\scripts\staging_up.ps1          (Linux: scripts/staging_up.sh)
docker compose -p cdr-staging -f docker-compose.prod.yml --env-file .env.staging exec backend python scripts/create_admin.py --username stagingadmin --full-name "Staging Admin" --email staging@example.com
```
Then open `https://localhost:8443`. The HTTP port (8080) redirects to the production address: always type the https address yourself. If the browser
will not go past the certificate warning (it remembers production's HSTS for the name `localhost`), use `https://127.0.0.1:8443`.

## Rehearse an upgrade
1. Put the new version of the files in place and run `staging_up` (it rebuilds; the migrations run on the staging database).
2. Check it: `docker compose -p cdr-staging -f docker-compose.prod.yml --env-file .env.staging exec backend python scripts/verify_db_constraints.py`
   (all protections present) and `... exec backend python scripts/system_check.py` (the System Status checks).
3. Sign in, try what changed. Only when staging is right, run `prod_up` for production.

## Stop, restart, erase
* Stop (data kept): `docker compose -p cdr-staging -f docker-compose.prod.yml --env-file .env.staging down`
* Start again: `staging_up` (safe to re-run).
* Erase staging's data: the same `down` with `-v` at the end. **Always include `-p cdr-staging`**: without it the command would address production.

## Limits (stated plainly)
* Same machine: a load test competes with production for the processor and memory, so run heavy tests when production is quiet, or on a separate machine.
* The certificate is self-signed (not trusted by browsers): expected for a rehearsal.
* Staging cannot prove how production behaves with its real volume of data; it proves the procedure and the code.
