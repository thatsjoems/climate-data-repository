# Database operations

How to keep the CDR database safe and recoverable. Commands are given for **Windows PowerShell**
(the way this project is normally run) and, where they differ, for bash. Run everything from the
folder that contains `docker-compose.yml`.

| Topic | Where |
|---|---|
| Back up and restore | sections 1-2 |
| Creating the first administrator (production) | section 3 |
| Closing the database to the network; least-privilege role; tamper-proof audit log | section 4 |
| Three database rules that were missing, and how to check the real database | section 5 |
| What none of this covers | section 6 |

> Nothing in `scripts/` or here has been run against a real PostgreSQL by the person who wrote it -
> there was no Docker in the environment it was written in. Treat the **restore drill** in section 2
> as mandatory before relying on any of it.

---

## 1. Back up

The data lives in two Docker volumes, and **both must be backed up together**: `cdr_postgres_data`
(the database) and `cdr_uploads` (the Excel files the database rows point at). A database restored
without its files leaves submissions that cannot be downloaded.

```powershell
.\scripts\backup.ps1                  # creates backups\<UTC timestamp>\
```
```bash
scripts/backup.sh                     # same, for bash / WSL / Linux
```

Each backup folder contains `db.dump`, `uploads.tar`, `SHA256SUMS` and `MANIFEST.txt`. The script checks
that the dump is readable before it keeps it, and never deletes older backups.

**Make it routine.** Run it on a schedule (Windows: *Task Scheduler* running
`powershell -File <repo>\scripts\backup.ps1` from the repository folder; Linux: `cron`), and **copy the
backup folders to a different machine or storage** - a backup on the same disk does not survive the
disk. Decide how long to keep them and delete older ones yourself.

**Danger to avoid:** `docker compose down -v` deletes the volumes - and with them all data. The ordinary
`docker compose down` is safe.

## 2. Restore

```powershell
.\scripts\restore.ps1 backups\20261005T101500Z
```
```bash
scripts/restore.sh backups/20261005T101500Z
```

It verifies the checksums, asks you to type `RESTORE`, stops the backend, restores the database, starts
the backend (which runs any migrations the backup is missing), then restores the uploaded files.
**This replaces the current data.**

Afterwards:

```powershell
docker compose exec backend python scripts/verify_db_constraints.py
```

### Restore drill - do this once, on a copy, before you trust the backups

1. Take a backup. 2. On another computer (or after `docker compose down -v` on a throw-away copy of the
project), start the stack and restore that backup. 3. Sign in, open a submission, download its file, and
run the verify script above. A backup that has never been restored is a hope, not a backup.

---

## 3. The first administrator in production

With `ENVIRONMENT=production` the system creates **no users** (the demo accounts have published
passwords), and the only user-creation feature requires an administrator already signed in. So on a new
production database, create the first administrator from the command line:

```powershell
docker compose exec backend python scripts/create_admin.py --username <name> --full-name "<Full Name>" --email <address>
```

It asks for the password twice at a hidden prompt (so it never appears in shell history). Run it in an
ordinary terminal - **do not add `-T`**. It refuses if the password is weak or the name/e-mail is taken.
It also refuses if an active System Administrator already exists; if the only administrator is locked
out or deactivated and nobody can sign in, add `--allow-additional`. Add `--must-change-password` to force
a change at the first sign-in. The event is recorded in the audit log (never the password).

> **Development / training mode** (the default `ENVIRONMENT`) still creates the demo accounts
> (`admin` / `Admin@123`, ...). Anything reachable by other people should run with
> `ENVIRONMENT=production`, a real `SECRET_KEY` and `POSTGRES_PASSWORD` (see `.env.docker.example`).

---

## 4. Closing the database down

### 4a. The port (already done)

`docker-compose.yml` now publishes the database as `127.0.0.1:5433`, i.e. on this machine only. Before
this it was `5433:5432`, which publishes it on **every** network interface, so anyone who could reach the
computer could try the password. The backend never needed that port - it uses `db:5432` inside Docker.
Local tools (`psql`, a GUI client) still work on `localhost:5433`.

### 4b. A restricted database role (optional - you opt in)

By default the backend connects as `postgres`, a superuser. So a flaw in the application can read, change
or **drop everything**, including the audit log, and "append-only" is only the application's promise.
This optional step makes the database enforce it. The restricted role `cdr_app` can read and write
ordinary data and nothing else: no superuser powers, no changing the table structure, **no DELETE**
(the application never issues one - checked), and **no UPDATE on `audit_logs` or `risk_advisory_notes`**.
Migrations still run, as the owner.

1. Make sure the stack has started at least once (the tables must exist). Make a password of letters and
   digits only:
   ```powershell
   $b = New-Object byte[] 24; [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($b)
   $pw = -join ($b | ForEach-Object { $_.ToString('x2') }); $pw
   ```
   ```bash
   PW=$(openssl rand -hex 24); echo "$PW"
   ```
2. Create the role (re-running is safe):
   ```powershell
   docker compose cp database/roles/create_app_role.sql db:/tmp/create_app_role.sql
   docker compose exec -T db sh -c "psql -U `$POSTGRES_USER -d `$POSTGRES_DB -v app_password=$pw -f /tmp/create_app_role.sql"
   docker compose exec -T db rm -f /tmp/create_app_role.sql
   ```
   ```bash
   docker compose cp database/roles/create_app_role.sql db:/tmp/create_app_role.sql
   docker compose exec -T db sh -c "psql -U \$POSTGRES_USER -d \$POSTGRES_DB -v app_password=$PW -f /tmp/create_app_role.sql"
   docker compose exec -T db rm -f /tmp/create_app_role.sql
   ```
3. In `.env` (next to `docker-compose.yml`) add `APP_DB_PASSWORD=<that password>`, and make sure
   `POSTGRES_PASSWORD` is set to a real password there too.
4. Copy `docker-compose.hardened.example.yml` to `docker-compose.override.yml` (Compose merges it in
   automatically), then `docker compose up -d --force-recreate backend`.
5. **Check it.** The application should work normally (sign in, upload, review), and the database should
   refuse to alter the audit log:
   ```powershell
   docker compose exec -it db psql -h localhost -U cdr_app -d climate_data_repository
   ```
   Enter the `cdr_app` password, then type `UPDATE audit_logs SET action = 'x';` - it **must** answer
   `ERROR: permission denied for table audit_logs`.

To go back, delete `docker-compose.override.yml` and recreate the backend. If a future feature genuinely
needs `DELETE` or more, add a specific `GRANT` rather than going back to the superuser.

---

## 5. Three database rules, and checking the real database

The code (`models.py`) declares rules that the database should enforce itself. The automated tests build
their own throw-away database straight from `models.py`, but the **real** PostgreSQL database is built
only by the migrations in `backend/alembic/versions/`. Three rules were declared in the code and created by
no migration, so tests passed while the real database lacked them:

| Rule | Meaning |
|---|---|
| `ck_submission_records_outstanding_le_loan` | a loan's outstanding principal cannot exceed the loan amount |
| `ck_submissions_record_counts_consistent` | row counts are not negative and valid + invalid <= total |
| `ck_submissions_version_number_positive` | version numbers start at 1 |

Migration `f4a9c2d71b05` adds them, **safely on a database that already holds data**: on PostgreSQL each is
added `NOT VALID` (enforced for every new or changed row, not re-checked against old ones) and validated
straight away if no old row breaks it. Nothing is deleted or rewritten. If some old rows do break a rule,
the backend log says how many (`docker compose logs backend`, look for `NOT VALID`); find and fix them, then
validate. In `psql` (`docker compose exec db psql -U postgres -d climate_data_repository`):

```sql
SELECT id, submission_id, row_number, loan_amount_tzs, outstanding_principal_tzs
  FROM submission_records WHERE outstanding_principal_tzs > loan_amount_tzs;
-- after correcting them:
ALTER TABLE submission_records VALIDATE CONSTRAINT ck_submission_records_outstanding_le_loan;
```

The upload validator was extended in the same change so that these rules (and the existing non-negative,
interest-rate and coordinate rules) are reported as visible, row-level errors **before** anything is stored.
Previously a value such as a negative loan amount or a latitude of 200 was kept even though its row was
flagged, and the database then rejected the whole upload with an unexplained HTTP 409.

**Check the real database at any time** - after upgrades and after restoring a backup:

```powershell
docker compose exec backend python scripts/verify_db_constraints.py
```

It lists any expected protection that is missing and warns about constraints still `NOT VALID`.
`backend/tests/test_schema_parity.py` fails the test run if the models, the migrations and this script ever
drift apart again.

---

## 6. What none of this covers

Being clear about the limits matters more than a long list of features:

- **Encryption at rest and in transit.** The data volume is not encrypted and the backend-to-database link
  is not TLS (it stays on Docker's internal network). Disk encryption and network policy are for the
  hosting environment to decide.
- **Row-level security.** Each institution's data is separated by the application's code (and tested), not
  by the database itself.
- **Retention.** Nothing purges expired refresh tokens, old notifications or old audit entries.
- **Time zones.** Timestamps are stored as UTC without a time-zone marker (`datetime.utcnow`).
- **User names** are case-sensitive: `Admin` and `admin` can both exist.
- **Backups** are only as good as the copy kept elsewhere and the last restore drill.

## Windows: "the script is not digitally signed"

PowerShell may refuse the `.ps1` scripts (`backup.ps1`, `restore.ps1`, `prod_up.ps1`) because the project came from a download or a
synced folder. Either mark them as trusted once:

    Unblock-File .\scripts\*.ps1

or run one script without changing any setting of the machine:

    powershell -ExecutionPolicy Bypass -File .\scripts\backup.ps1

The second form affects only that command. The `.sh` scripts and the Python scripts are not affected.
