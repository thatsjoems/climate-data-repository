# Backup and recovery (production)

One tool does it all, on Windows and Linux, with only Python 3 and Docker: `scripts/prod_ops.py`.

| Command | What it does |
|---|---|
| `python scripts/prod_ops.py backup [--keep 14] [--copy-to <folder>]` | Dumps the database and the uploaded files from the same moment into `backups/prod/<UTC time>/`, with `SHA256SUMS` and `MANIFEST.txt`. Checks its own result (checksums and dump header), copies it off the machine if `--copy-to` is given and checks that copy too, then removes backups beyond the newest `--keep` (default 14). **If the off-machine copy fails** (drive missing, share disconnected), the local backup still stands and retention still runs; the tool prints a clear warning, writes `COPY-FAILED` in `backups/prod/backup.log` and exits with code 1, and `status` keeps warning until a backup is copied successfully. It only ever removes folders named like a timestamp inside the backup folder, and never the one it just made. |
| `python scripts/prod_ops.py status` | Shows the newest backup, its age and whether it still matches its checksums. Exit code 1 if there is none, it is older than 26 hours, or it is damaged: use it from monitoring. |
| `python scripts/prod_ops.py drill [--backup <folder>]` | **Restore drill.** Restores a backup into a throw-away copy of the stack (project `cdr-drill`, its own volumes, no published ports), checks it, removes it. Production is not touched. |
| `python scripts/prod_ops.py restore <backup folder>` | **Destructive.** Replaces the production database and uploads. Needs you to type `RESTORE-PRODUCTION`, takes a safety backup of the current state first, and verifies afterwards. |
| `python scripts/prod_ops.py schedule [--time 02:00] [--copy-to <folder>]` | Windows: registers a daily task "CDR-Backup". Linux: prints the `cron` line to add. `--remove` deletes the task. |

## First time

1. `python scripts/prod_ops.py backup --copy-to <a folder on ANOTHER disk or a network share>` (on Windows, `Get-PSDrive -PSProvider FileSystem` lists the drives that exist; a second folder on the same disk is not off-machine)
2. `python scripts/prod_ops.py drill` and read the result (below).
3. `python scripts/prod_ops.py schedule --time 02:00 --copy-to <same folder>`
4. A week later: `python scripts/prod_ops.py status`.

## What the drill checks

| Check | Passes when |
|---|---|
| database protections | `verify_db_constraints.py` reports all expected protections on the restored database |
| rows | printed for your eyes: users, institutions, submissions and audit entries |
| `cdr_app` rights | no UPDATE on the audit log, INSERT allowed, UPDATE allowed and no DELETE on submissions (`f|t|t|f`): the append-only rule survived the restore |
| uploaded files | the files were restored (count printed) |

Also printed: that the production containers are still there, the database size and how long the whole drill took. **Write that
time down: it is your measured recovery time on this hardware** (the Bank's recovery objectives are decision TBD-03).
The drill ends with `RESTORE DRILL: PASSED` or `FAILED` and an exit code of 0 or 1. It removes the throw-away copy either way.

## Recovery point and recovery time

- **Recovery point** (how much work can be lost) equals the interval between backups: a daily backup means up to a day.
- **Recovery time** is what the drill measured, plus the time to find the backup and decide.
- Neither is a promise until the Bank sets its objectives (TBD-03) and the drill is repeated regularly, for example monthly and after every update.

## In a real disaster

1. Keep the backup you will use and, if the old database still exists, do not delete it.
2. `python scripts/prod_ops.py restore backups/prod/<folder>` (or the off-machine copy).
3. Sign in, open the dashboard and Submission Status, and compare with what you expect before announcing it.
4. If the whole server is gone: install Docker, restore the project files, `.env.production` and `certs/` from your own secure copy
   (they are not in the backup, on purpose), run `scripts/prod_up.ps1` or `.sh`, then `restore`.

## Rules

- A backup on the machine it protects does not survive that machine: always use `--copy-to`.
- Never `docker compose down -v` on production. The drill is safe because it names its own project (`cdr-drill`) and refuses to remove any other.
- The backup holds real data. `backups/` is ignored by git. Protect copies like the database itself.
- A backup that has never been restored is not proven: repeat the drill.

## Measured results (project owner's machine, 6 October 2026)

| Run | Backup | Result | Time |
|---|---|---|---|
| Drill of the production backup | 56 KB database, 1 uploaded file | PASSED: 37 protections, rows 1 user, 0 institutions, 0 submissions, 2 audit entries; `cdr_app` rights `f|t|t|f`; 1 file | 50 s |
| Drill of a development backup (real size) | 15.0 MB database, 34 files | PASSED: 37 protections, rows 4 users, 4 institutions, 5 submissions, 124 audit entries; `cdr_app` rights `f|t|t|f`; 34 files | 48 s |

Both ran in a throw-away copy; the three production containers were untouched. The time includes building the backend image and
starting the copy, so it is a fair first measure of recovery time for a database of this size, not a guarantee for a larger one.
The daily task "CDR-Backup" (02:00) was registered and `status` reported the newest backup as intact.
