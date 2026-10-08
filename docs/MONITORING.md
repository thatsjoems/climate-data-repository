# Monitoring and alerts

The system checks itself and tells the System Administrators when something needs attention. There is **no e-mail or SMS** in this deployment, so
alerts appear in three places: the **System Status** page, the **bell** in the application (for System Administrators), and the **exit code**
of a command for the host's own scheduler or monitoring tool.

## What is checked
| Check | Attention (WARN) | Urgent (CRITICAL) |
|---|---|---|
| Database | answers in more than 500 ms | not reachable (the page itself fails) |
| Database schema version | | the database is not at the version the application expects |
| Backups | newest backup copied nowhere off the machine, or the copy failed | **no backup recorded**, or the newest is older than 26 hours, or its status file cannot be read |
| Disk space | less than 20% free | less than 10% free |
| Failed sign-ins (last hour) | 10 or more failures, or 2 accounts locked | 30 or more failures, or 5 accounts locked |
| Refused API keys (last hour) | 20 or more | 100 or more |
| Locked accounts (now) | 3 or more | |
| API keys | one expires within 14 days, or expired in the last 30 days and was not revoked | |
| Administrators | only one active System Administrator | none |

The limits are settings (`BACKUP_MAX_AGE_HOURS`, `ALERT_SIGNIN_FAILURES_WARN`, `ALERT_SIGNIN_FAILURES_CRITICAL`, `ALERT_DISK_FREE_WARN_PERCENT`,
`ALERT_DISK_FREE_CRITICAL_PERCENT`). A check that itself cannot run is shown as attention ("could not be checked"), never as a broken page.

## Where to look
1. **Administration, System Status**: all checks with what they found, refreshed every minute; "Details" shows the numbers behind each.
2. **The bell** (System Administrators): every few minutes (`MONITOR_INTERVAL_MINUTES`, 10 in production, 0 = off) the checks run and anything
   that needs attention becomes a notification. An **urgent** alert is told again after a day, an **attention** one after a week, and a change
   of severity at once, so the bell is not filled with the same message.
3. **From the host**, for a scheduler or a monitoring tool: `python scripts/prod_ops.py check` prints the checks and exits **0** (all fine),
   **1** (something to look at) or **2** (urgent, or the check could not run because production is down).

## How the backup reaches the application
The backup task runs on the host (`scripts/prod_ops.py backup`, scheduled daily). After each backup it writes one small file, `backups/status/last_backup.json`
(when, result, size, whether it was copied off the machine). That folder, and only that folder, is mounted **read-only** into the backend. The
backend therefore cannot read or change the backups themselves. It can tell that a backup did not happen; it cannot check the backup's integrity:
`prod_ops.py status` (checksums) and `prod_ops.py drill` (a real restore) do that on the host.

**After deploying this for the first time the page shows "No backup recorded" (urgent) until a backup runs**: run `python scripts/prod_ops.py backup`
once (with your usual `--copy-to`). The same applies after a new machine: nothing is hidden.

## Limits (stated plainly)
* **If the backend is down it cannot alert.** Watch it from outside: `prod_ops.py check` returns 2 when the backend cannot be reached, and `GET /api/health`
  is a plain liveness check for any uptime tool.
* Alerts reach people who open the application. Nobody is called or e-mailed; that needs an e-mail/SMS service from BOT ICT.
* Failed sign-ins are counted for **existing** accounts (wrong password or code). A wrong username is not recorded (the rate limit covers it).
* Disk space is the disk the backend sees. The database's own disk is the same machine in this setup; a separate database server needs its own monitoring.
* Several backend workers would each run the monitor; the notifications are de-duplicated in the database, but at the same moment two could still both be sent.

## Settings
`MONITOR_INTERVAL_MINUTES` (0 = background monitor off), `BACKUP_STATUS_DIR`, `BACKUP_MAX_AGE_HOURS`, `ALERT_*` as above. Production defaults are in
`docker-compose.prod.yml`; the production checker requires the monitor setting and the read-only status mount.

## What was verified
Each check on its own with its edges (exactly at a limit, in the future, unreadable, missing), the alert de-duplication and severity change, the background
monitor starting, repeating, surviving a failed run and stopping cleanly, and that the host's status file and the application's reader agree. The page is
for the System Administrator only and shows no stored secret. Tests: `tests/test_monitoring.py`.
