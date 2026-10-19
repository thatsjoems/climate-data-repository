# Backup and recovery (production)

One tool does it all, on Windows and Linux, with only Python 3 and Docker: `scripts/prod_ops.py`.

| Command | What it does |
|---|---|
| `python scripts/prod_ops.py backup [--keep 14] [--copy-to <folder>] [--purge] [--wait-docker 10] [--retries 2]` | Dumps the database and the uploaded files from the same moment into `backups/prod/<UTC time>/`, with `SHA256SUMS` and `MANIFEST.txt`. Checks its own result (checksums and dump header), copies it off the machine if `--copy-to` is given and checks that copy too, then removes backups beyond the newest `--keep` (default 14). **If the off-machine copy fails** (drive missing, share disconnected), the local backup still stands and retention still runs; the tool prints a clear warning, writes `COPY-FAILED` in `backups/prod/backup.log` and exits with code 1, and `status` keeps warning until a backup is copied successfully. It only ever removes folders named like a timestamp inside the backup folder, and never the one it just made. With `--purge`, once the backup exists it also runs the housekeeping (`purge --apply`: expired refresh tokens and old notifications; audit logs are never touched); a housekeeping failure never changes the backup's exit code. |
| `python scripts/prod_ops.py status` | Shows the newest backup, its age and whether it still matches its checksums. Exit code 1 if there is none, it is older than 26 hours, or it is damaged: use it from monitoring. |
| `python scripts/prod_ops.py drill [--backup <folder>]` | **Restore drill.** Restores a backup into a throw-away copy of the stack (project `cdr-drill`, its own volumes, no published ports), checks it, removes it. Production is not touched. |
| `python scripts/prod_ops.py restore <backup folder>` | **Destructive.** Replaces the production database and uploads. Needs you to type `RESTORE-PRODUCTION`, takes a safety backup of the current state first, and verifies afterwards. |
| `python scripts/prod_ops.py schedule [--time 02:00] [--copy-to <folder>]` | Windows: registers a daily task "CDR-Backup" (backup, then housekeeping; `--no-purge` for the backup alone). The task is allowed to start on battery, not to stop when the computer goes onto battery, to run after a missed start, to wake the computer, and to restart up to 3 times; its command waits up to 10 minutes for Docker Desktop (starting it if needed) and tries the backup again twice, 5 minutes apart. Its messages go to `backups/prod/scheduled_run.log` (never to `backup.log`, which the tool itself appends to). Linux: prints the `cron` line to add. `--remove` deletes the task. |

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
The drill builds its own copy of the backend image every time (`--build`): on 11 October 2026 a first drill failed with "Can't locate revision f3a7c1e5b829" because it had reused an older drill image that did not know the newest migration. The second drill that day failed at the uploaded files: the restore ran as root inside the hardened container (which cannot override file permissions) on a folder owned by the application's own user, so tar could neither replace nor date the files. The files are now restored as that user. This would also have broken a real `restore`, which is why the drill matters.
If a drill fails at the backend step, its message now ends with the last lines of the backend's log.
The drill ends with `RESTORE DRILL: PASSED` or `FAILED` and an exit code of 0 or 1. It removes the throw-away copy either way.

## Measured result

| Date | Backup restored | Result | Whole drill |
|---|---|---|---|
| 11 October 2026 (owner's computer, Docker Desktop on Windows) | `20261011T150027Z`: database 0.07 MB, uploads almost empty | **PASSED**: all 47 database protections present; rows users 3, institutions 0, submissions 0, audit entries 39; `cdr_app` rights `f|t|t|f`; 1 uploaded file restored | **37 s** |

**Read this number with care.** It measures the steps (start a database, restore, start the backend, check), not a large database: the data was almost empty. With real submissions the restore step grows with the size of the dump, so the drill must be repeated when the data has grown, and after every update. The first two drills of that day failed for reasons found and fixed (see below), which is what a drill is for.

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


## What was learned from the first scheduled runs (15 to 19 October 2026)

| Date (02:00 local) | Result | Cause | Fix |
|---|---|---|---|
| 16 Oct | Backup written and copied; task ended with `3221225786` (process terminated) | Docker stopped while housekeeping ran | Housekeeping failure never affects the backup; Docker wait and retries |
| 17 Oct | Did not run at 02:00; ran at about 10:08 and failed | The computer was off or asleep; the catch-up run started before Docker was ready | `--wait-docker 10` starts Docker Desktop and waits; `--retries 2` |
| 18 Oct | Failed (exit code 1): "failed to connect to the docker API" | Docker Desktop was not running | Same |
| 19 Oct | **Succeeded (`LastTaskResult 0`)**: backup `20261018T230002Z` copied off the machine, housekeeping ran | The computer and Docker Desktop were up | Confirmed |

A failed attempt now removes its own half-made dated folder (an empty folder used to count as a backup in the retention count). A locked `backup.log` is reported as a warning and never fails the backup.

Limits that no script can remove: a computer that is switched off at 02:00 cannot run anything (the task catches up when it is next on), and the task runs while the user is signed in to Windows. A production server that is always on, with the service set to start Docker at boot, makes both limits disappear. Unit tests for these rules need only Python: `python -m unittest scripts/test_prod_ops.py -v`.
