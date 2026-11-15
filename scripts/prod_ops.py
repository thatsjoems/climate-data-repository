#!/usr/bin/env python3
"""
Backup, status, restore drill, restore and scheduling for the PRODUCTION stack (docker-compose.prod.yml).

    python scripts/prod_ops.py backup  [--out backups/prod] [--keep 14] [--copy-to <folder>] [--purge] [--wait-docker 10] [--retries 2]
    python scripts/prod_ops.py status  [--out backups/prod] [--max-age-hours 26]
    python scripts/prod_ops.py purge   [--apply]                 (housekeeping: expired refresh tokens, old notifications; dry run unless --apply)
    python scripts/prod_ops.py check     (the System Status checks; exit code 0 fine, 1 attention, 2 urgent)
    python scripts/prod_ops.py drill   [--backup <folder>] [--keep-drill]
    python scripts/prod_ops.py restore <backup folder>            (DESTRUCTIVE - replaces production data)
    python scripts/prod_ops.py schedule [--time 02:00] [--remove]  (Windows Task Scheduler; prints a cron line elsewhere)

REHEARSAL ON STAGING. Every command except `schedule` also takes --stack staging (before or after the command name), which points it at the rehearsal copy
(docs/STAGING.md): project cdr-staging, .env.staging, backups in backups/staging, and its status file in backups/staging-status. Without --stack nothing changes:
the target is production, exactly as before. The scheduled task never passes --stack, so it can only ever back up production. Staging is disposable and
holds synthetic data only; use it to practise backup, drill and restore (for example on Linux) before doing them on production.

Needs only Python 3 and Docker. A backup holds the database dump and the uploaded files from the same moment,
with SHA256SUMS and a MANIFEST (same layout as scripts/backup.ps1, so either restore script can read it).

THE DRILL restores a backup into a throw-away copy of the stack (its own project name, cdr-drill, its own volumes,
no published ports), checks it, and removes it. It never touches production: every command it runs names the
project cdr-drill, and the one destructive command (down -v) refuses to run for any other project.
"""
import argparse
import datetime
import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
PROD, DRILL, STAGING = "cdr-prod", "cdr-drill", "cdr-staging"
# What each stack is called, where its secrets and backups live. ACTIVE is production unless main() is given --stack staging.
STACKS = {
    "production": {"name": "production", "project": PROD, "env": ".env.production", "out": "backups/prod", "status": "status"},
    "staging": {"name": "staging", "project": STAGING, "env": ".env.staging", "out": "backups/staging", "status": "staging-status"},
}
ACTIVE = dict(STACKS["production"])


def use_stack(name):
    """Point every command at one stack. Only main() calls this."""
    ACTIVE.clear()
    ACTIVE.update(STACKS[name])
STAMP = re.compile(r"^\d{8}T\d{6}Z$")
SLEEP = float(os.environ.get("CDR_OPS_SLEEP", "5"))
ROLE_SQL, BARE_ROLE_SQL = "database/roles/create_app_role.sql", "database/roles/create_bare_role.sql"
EXPECTED_PRIVILEGES = "f|t|t|f"   # cdr_app: no UPDATE on audit_logs, INSERT yes; UPDATE yes and DELETE no on submissions


class Fail(Exception):
    pass


SCHEDULED_LOG = "scheduled_run.log"      # what the scheduler's command line writes to. NEVER backup.log: prod_ops itself appends to that file,
                                          # and Windows refuses a second writer ("PermissionError ... backup.log").
DOCKER_EXE = r"C:\Program Files\Docker\Docker\Docker Desktop.exe"


def docker_ready():
    try:
        return subprocess.run(["docker", "info"], capture_output=True, timeout=30).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def ensure_docker(minutes):
    """
    A scheduled backup can start before Docker Desktop is ready (after a wake-up, a restart, or when it was closed):
    the log then says 'failed to connect to the docker API ... dockerDesktopLinuxEngine'. Wait up to `minutes`, and on Windows
    start Docker Desktop once if it is not running. Returns True when Docker answers.
    """
    if minutes <= 0 or docker_ready():
        return True
    print(f"Docker is not answering. Waiting up to {minutes} minute(s) for it ...")
    if os.name == "nt" and os.path.isfile(DOCKER_EXE):
        print("  starting Docker Desktop ...")
        subprocess.Popen([DOCKER_EXE], close_fds=True, creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
    deadline = time.time() + minutes * 60
    while time.time() < deadline:
        time.sleep(min(10, SLEEP * 2))
        if docker_ready():
            print("  Docker is ready.")
            return True
    print("  Docker did not become ready in time.")
    return False


def append_log(out_dir, line):
    """The one-line history in backup.log. A locked or unwritable log must never turn a good backup into a failure."""
    try:
        with open(pathlib.Path(out_dir) / "backup.log", "a", encoding="utf-8") as log:
            log.write(line)
    except OSError as exc:
        print(f"  WARNING: could not write backup.log ({exc.strerror or exc}); the backup itself is fine.")


def compose(args, project=None, capture=False, check=True):
    project = project or ACTIVE["project"]
    cmd = ["docker", "compose", "-p", project, "-f", "docker-compose.prod.yml", "--env-file", ACTIVE["env"], *args]
    r = subprocess.run(cmd, cwd=ROOT, capture_output=capture, text=True)
    if check and r.returncode != 0:
        tail = (r.stderr or "").strip()[-300:] if capture else ""
        raise Fail(f"docker compose {' '.join(args[:3])} ... failed (exit {r.returncode}) {tail}".strip())
    return r


def sh_in(service, script, project=None, capture=False):
    return compose(["exec", "-T", service, "sh", "-c", script], project, capture=capture)


def wait_healthy(service, project, tries=60):
    for _ in range(tries):
        cid = compose(["ps", "-q", service], project, capture=True, check=False).stdout.strip()
        if cid:
            st = subprocess.run(["docker", "inspect", "--format", "{{.State.Health.Status}}", cid], capture_output=True, text=True).stdout.strip()
            if st == "healthy":
                return
        time.sleep(SLEEP)
    tail = compose(["logs", "--tail", "12", service], project, capture=True, check=False).stdout.strip()
    raise Fail(f"{service} ({project}) did not become healthy. Last lines of its log:\n{tail}")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def verify_sums(folder):
    """Check db.dump and uploads.tar against SHA256SUMS. Returns the list of problems (empty = fine)."""
    folder = pathlib.Path(folder)
    problems = []
    for f in ("db.dump", "uploads.tar", "SHA256SUMS"):
        if not (folder / f).is_file():
            problems.append(f"{f} is missing")
    if problems:
        return problems
    for line in (folder / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        if line.strip():
            expected, name = line.split(None, 1)
            name = name.strip().lstrip("*")
            if sha256(folder / name) != expected.lower():
                problems.append(f"checksum mismatch for {name}")
    with open(folder / "db.dump", "rb") as f:
        if f.read(5) != b"PGDMP":
            problems.append("db.dump is not a PostgreSQL custom-format dump")
    if (folder / "db.dump").stat().st_size < 1000 and os.environ.get("CDR_OPS_TEST") != "1":
        problems.append("db.dump is suspiciously small")
    return problems


def apply_sql(project, rel, with_password=True):
    name = pathlib.Path(rel).name
    compose(["cp", rel, f"db:/tmp/{name}"], project)
    sh_in("db", f"psql -U $POSTGRES_USER -d $POSTGRES_DB -v ON_ERROR_STOP=1 -v app_password=$APP_DB_PASSWORD -f /tmp/{name}", project)
    compose(["exec", "-T", "db", "rm", "-f", f"/tmp/{name}"], project)


def restore_dump(project, folder):
    folder = pathlib.Path(folder)
    apply_sql(project, BARE_ROLE_SQL)                              # the role must exist before its grants are restored
    compose(["cp", str(folder / "db.dump"), "db:/tmp/cdr.dump"], project)
    sh_in("db", "pg_restore -U $POSTGRES_USER -d $POSTGRES_DB --clean --if-exists --no-owner /tmp/cdr.dump", project)
    compose(["exec", "-T", "db", "rm", "-f", "/tmp/cdr.dump"], project)
    apply_sql(project, ROLE_SQL)                                    # re-apply the least-privilege grants and the audit-table revokes


def restore_uploads(project, folder):
    # The backend container is hardened (docs/DOCKER.md): its root has no right to override file permissions, and /app/uploads belongs to the
    # application's own user (cdr). So the emptying and the unpacking run AS cdr, which owns the folder; root only fixes the copied archive's mode and
    # removes it afterwards (it owns that file in /tmp). Run as root, tar failed with "Cannot open: File exists" and "Cannot utime", and `rm -rf /app/uploads/*`
    # could not have removed real files either. `find ... -delete` also removes hidden files, which `*` does not match.
    # On Windows the copied archive belongs to root inside the container, so root can change its mode and remove it. On Linux `docker compose cp` keeps the
    # owner of the file on the host (found on Ubuntu, 15 November 2026: "chmod: Operation not permitted"), and the hardened container's root may not change or
    # remove a file that is not its own (/tmp is sticky). Both steps are therefore best effort: the archive is readable by everyone when the host created it
    # with the usual mode (644 or 664), and if cdr still cannot read it the unpacking step below fails with a clear message. A leftover archive in /tmp
    # disappears when the container is replaced.
    compose(["cp", str(pathlib.Path(folder) / "uploads.tar"), "backend:/tmp/uploads.tar"], project)
    if compose(["exec", "-T", "backend", "chmod", "644", "/tmp/uploads.tar"], project, capture=True, check=False).returncode != 0:
        print("  (note: the mode of the copied archive could not be changed; continuing, the next step shows whether it can be read)")
    compose(["exec", "-T", "-u", "cdr", "backend", "sh", "-c", "find /app/uploads -mindepth 1 -delete && tar -C /app -xf /tmp/uploads.tar"], project)
    compose(["exec", "-T", "backend", "rm", "-f", "/tmp/uploads.tar"], project, capture=True, check=False)


# ------------------------------------------------------------------------------------------------ backup
def make_backup(out_dir, keep, copy_to=None):
    out_dir = pathlib.Path(out_dir)
    out_dir = out_dir if out_dir.is_absolute() else ROOT / out_dir
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    folder = out_dir / stamp
    folder.mkdir(parents=True, exist_ok=True)
    print(f"Backing up {ACTIVE['name']} to {folder} ...")
    try:
        return _take_backup(out_dir, keep, copy_to, stamp, folder)
    except BaseException:
        # A failed attempt must leave nothing behind: an empty or half-filled dated folder would count as a backup in the retention
        # count and could push a good one out.
        shutil.rmtree(folder, ignore_errors=True)
        raise


def _take_backup(out_dir, keep, copy_to, stamp, folder):
    sh_in("db", "pg_dump -U $POSTGRES_USER -d $POSTGRES_DB -Fc -f /tmp/cdr.dump")
    sh_in("db", "pg_restore --list /tmp/cdr.dump > /dev/null")                  # proves the dump is readable
    compose(["cp", "db:/tmp/cdr.dump", str(folder / "db.dump")])
    compose(["exec", "-T", "db", "rm", "-f", "/tmp/cdr.dump"])
    compose(["exec", "-T", "backend", "tar", "-C", "/app", "-cf", "/tmp/uploads.tar", "uploads"])
    compose(["cp", "backend:/tmp/uploads.tar", str(folder / "uploads.tar")])
    compose(["exec", "-T", "backend", "rm", "-f", "/tmp/uploads.tar"])
    sums = [f"{sha256(folder / n)}  {n}" for n in ("db.dump", "uploads.tar")]
    (folder / "SHA256SUMS").write_text("\n".join(sums) + "\n", encoding="utf-8", newline="\n")
    revision = "unknown"
    r = compose(["exec", "-T", "backend", "sh", "-c", "cd /app && python -m alembic current 2>/dev/null"], capture=True, check=False)
    if r.returncode == 0 and r.stdout.strip():
        revision = r.stdout.strip().splitlines()[-1].strip()
    manifest = [f"CDR backup ({ACTIVE['name']})", f"taken (UTC):     {stamp}", f"schema revision: {revision}", "files:"]
    manifest += [f"  {p.stat().st_size:>12}  {p.name}" for p in sorted(folder.iterdir())]
    (folder / "MANIFEST.txt").write_text("\n".join(manifest) + "\n", encoding="utf-8", newline="\n")
    problems = verify_sums(folder)
    if problems:
        raise Fail("The new backup failed its own check: " + "; ".join(problems))
    print(f"  checked: checksums and dump header are fine ({(folder / 'db.dump').stat().st_size:,} bytes database, {(folder / 'uploads.tar').stat().st_size:,} bytes files)")
    copy_error = None
    if copy_to:
        dest = pathlib.Path(copy_to) / stamp
        try:
            shutil.copytree(folder, dest)
            problems = verify_sums(dest)
            if problems:
                copy_error = f"the copy at {dest} failed its check: " + "; ".join(problems)
            else:
                print(f"  copied and checked off-machine: {dest}")
        except OSError as exc:
            copy_error = (f"cannot write to {copy_to} ({exc.strerror or exc}). Does that drive or network share exist and is it connected? "
                          "The local backup is safe; only the off-machine copy is missing.")
        if copy_error:
            print(f"  WARNING: off-machine copy FAILED: {copy_error}")
    else:
        print("  NOTE: no --copy-to given. A backup on the same disk does not survive the disk.")
    removed = prune(out_dir, keep, folder)
    if removed:
        print(f"  retention: kept the newest {keep}, removed {len(removed)} older: {', '.join(removed)}")
    append_log(out_dir, f"{stamp} {'COPY-FAILED' if copy_error else 'OK'} {folder.name} revision={revision}\n")
    write_status(out_dir, stamp, folder, revision, copy_to, copy_error)
    print("Done (local backup OK)." if copy_error else "Done.")
    return folder, copy_error


def write_status(out_dir, stamp, folder, revision, copy_to, copy_error):
    """
    Leaves the result of the backup in <backups>/status/last_backup.json, a folder that the production backend can READ (and nothing else
    of the backups: only this small file). The System Status page and the alerts use it to notice a backup that did not happen.
    """
    status_dir = pathlib.Path(out_dir).parent / ACTIVE["status"]      # staging has its own: it must never overwrite the file production's monitoring reads
    status_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "taken_utc": stamp, "result": "COPY-FAILED" if copy_error else "OK", "revision": revision,
        "database_bytes": (folder / "db.dump").stat().st_size, "uploads_bytes": (folder / "uploads.tar").stat().st_size,
        "off_machine": bool(copy_to) and not copy_error, "copy_error": copy_error,
    }
    tmp = status_dir / "last_backup.json.tmp"
    tmp.write_text(json.dumps(data), encoding="utf-8")
    tmp.replace(status_dir / "last_backup.json")        # replaced in one step: the application never reads half a file


def prune(out_dir, keep, protect):
    dirs = sorted((d for d in out_dir.iterdir() if d.is_dir() and STAMP.match(d.name)), key=lambda d: d.name)
    old = [d for d in (dirs[:-keep] if keep > 0 and len(dirs) > keep else []) if d != protect]
    for d in old:
        shutil.rmtree(d)
    return [d.name for d in old]


def newest_backup(out_dir):
    out_dir = pathlib.Path(out_dir)
    out_dir = out_dir if out_dir.is_absolute() else ROOT / out_dir
    dirs = sorted((d for d in out_dir.iterdir() if d.is_dir() and STAMP.match(d.name)), key=lambda d: d.name) if out_dir.is_dir() else []
    return dirs[-1] if dirs else None


def backup_with_retries(a):
    """Wait for Docker, then try up to 1 + a.retries times, pausing a.retry_wait minutes between tries."""
    tries = 1 + max(0, getattr(a, "retries", 0))
    for n in range(1, tries + 1):
        if ensure_docker(getattr(a, "wait_docker", 0)):
            try:
                return make_backup(a.out, a.keep, a.copy_to)
            except Fail as exc:
                if n == tries:
                    raise
                reason = str(exc)
        else:
            reason = "Docker is not running"
            if n == tries:
                raise Fail("Docker is not running (waited as asked). Start Docker Desktop; the next scheduled run will try again.")
        wait = getattr(a, "retry_wait", 5)
        print(f"Attempt {n} of {tries} failed: {reason}\nTrying again in {wait:g} minute(s) ...")
        time.sleep(wait * 60 if wait > 0 else 0)


def cmd_backup(a):
    _, copy_error = backup_with_retries(a)
    if getattr(a, "purge", False):
        # Housekeeping runs only AFTER a backup exists (so nothing is ever removed without a fresh copy), and a failure here
        # never changes the backup's own exit code: the backup is what monitoring watches.
        print("Housekeeping (expired refresh tokens, old notifications) ...")
        try:
            if cmd_purge(argparse.Namespace(apply=True)):
                print("WARNING: housekeeping did not run (see the message above). The backup itself is fine. If the message says the script is missing, "
                      "the backend image is older than this package: run scripts\\prod_up.ps1 to rebuild it.")
        except Exception as e:     # noqa: BLE001 - report and carry on
            print(f"Housekeeping skipped: {e}")
    return 1 if copy_error else 0   # exit code 1 lets the scheduler and monitoring see a missing off-machine copy


def cmd_status(a):
    newest = newest_backup(a.out)
    if not newest:
        print(f"NO BACKUP found in {a.out}. Run: python scripts/prod_ops.py backup")
        return 1
    taken = datetime.datetime.strptime(newest.name, "%Y%m%dT%H%M%SZ").replace(tzinfo=datetime.timezone.utc)
    age = (datetime.datetime.now(datetime.timezone.utc) - taken).total_seconds() / 3600
    count = len([d for d in newest.parent.iterdir() if d.is_dir() and STAMP.match(d.name)])
    problems = verify_sums(newest)
    print(f"Newest backup: {newest.name} ({age:.1f} hours old); {count} backup(s) kept; integrity: {'OK' if not problems else 'PROBLEM: ' + '; '.join(problems)}")
    log = newest.parent / "backup.log"
    last = log.read_text(encoding="utf-8").strip().splitlines()[-1] if log.is_file() and log.read_text(encoding="utf-8").strip() else ""
    if "COPY-FAILED" in last:
        print("WARNING: the last backup could not be copied off the machine (see backup.log).")
        return 1
    if age > a.max_age_hours:
        print(f"WARNING: older than {a.max_age_hours} hours - the scheduled backup may not be running.")
        return 1
    return 1 if problems else 0


def cmd_check(a):
    """The checks of the System Status page (database, schema, backups, disk, failed sign-ins, keys, administrators), for a scheduler or a monitor."""
    r = compose(["exec", "-T", "backend", "python", "scripts/system_check.py"], capture=True, check=False)
    out = r.stdout or ""
    print(out, end="")
    if "SYSTEM CHECK" not in out:                      # docker itself failed (production not running): do not pretend that is "attention"
        print("The check could not run inside the backend. Is production up?  " + (r.stderr or "").strip()[-200:])
        return 2
    return r.returncode        # 0 all fine, 1 attention, 2 urgent


def cmd_purge(a):
    """Housekeeping inside the backend container (it deletes with the owner role; the application's role cannot delete). Dry run unless --apply."""
    cmd = ["exec", "-T", "backend", "python", "scripts/purge_old_data.py"] + (["--apply"] if a.apply else [])
    r = compose(cmd, capture=True, check=False)
    print((r.stdout or "").strip() or (r.stderr or "").strip()[-300:])
    return r.returncode


# ------------------------------------------------------------------------------------------------ drill and restore
def counts(project):
    q = "select (select count(*) from users), (select count(*) from institutions), (select count(*) from submissions), (select count(*) from audit_logs)"
    return sh_in("db", f'psql -U $POSTGRES_USER -d $POSTGRES_DB -tA -F"|" -c "{q}"', project, capture=True).stdout.strip()


def privileges(project):
    q = ("select has_table_privilege('cdr_app','audit_logs','UPDATE'), has_table_privilege('cdr_app','audit_logs','INSERT'), "
         "has_table_privilege('cdr_app','submissions','UPDATE'), has_table_privilege('cdr_app','submissions','DELETE')")
    out = sh_in("db", f'psql -U $POSTGRES_USER -d $POSTGRES_DB -tA -F"|" -c "{q}"', project, capture=True).stdout.strip()
    return out.replace("true", "t").replace("false", "f")


def teardown_drill():
    project = DRILL
    assert project == DRILL and project not in (PROD, STAGING), "refusing to remove anything but the drill project"
    compose(["down", "-v", "--remove-orphans"], project, check=False)


def cmd_drill(a):
    folder = pathlib.Path(a.backup) if a.backup else newest_backup(ACTIVE["out"])
    if folder is None:
        print("No backup to test. Take one first: python scripts/prod_ops.py backup (or give --backup <folder>).")
        return 2
    folder = folder if folder.is_absolute() else ROOT / folder
    problems = verify_sums(folder)
    if problems:
        print("The backup is damaged, so the drill stops here:", "; ".join(problems))
        return 1
    print(f"RESTORE DRILL of {folder.name} ({ACTIVE['name']}) into a throw-away copy (project {DRILL}). The {ACTIVE['name']} stack itself is not touched.")
    started = time.time()
    results, ok = [], True
    try:
        compose(["up", "-d", "db"], DRILL)
        wait_healthy("db", DRILL)
        restore_dump(DRILL, folder)
        # --build: the drill has its own image (cdr-drill-backend). Without it an image left by an earlier drill is reused, with older code
        # that does not know the newest migrations ("Can't locate revision ..."), and the drill fails for a reason that has nothing to do with the backup.
        compose(["up", "-d", "--build", "backend"], DRILL)
        wait_healthy("backend", DRILL)
        restore_uploads(DRILL, folder)
        verify = compose(["exec", "-T", "backend", "python", "scripts/verify_db_constraints.py"], DRILL, capture=True, check=False)
        results.append(("database protections", verify.stdout.strip().splitlines()[-1] if verify.stdout.strip() else "(no output)", verify.returncode == 0 and "OK:" in verify.stdout))
        results.append(("rows (users|institutions|submissions|audit)", counts(DRILL), True))
        priv = privileges(DRILL)
        results.append(("cdr_app rights (audit UPDATE|audit INSERT|submissions UPDATE|submissions DELETE)", priv, priv == EXPECTED_PRIVILEGES))
        tar_files = compose(["exec", "-T", "backend", "sh", "-c", "find /app/uploads -type f | wc -l"], DRILL, capture=True).stdout.strip()
        results.append(("uploaded files restored", tar_files, True))
        ok = all(r[2] for r in results)
    except Fail as exc:
        print("DRILL STEP FAILED:", exc)
        ok = False
    finally:
        if a.keep_drill:
            print(f"The drill stack was left running (project {DRILL}). Remove it with: docker compose -p {DRILL} -f docker-compose.prod.yml --env-file {ACTIVE['env']} down -v")
        else:
            teardown_drill()
    seconds = time.time() - started
    for name, value, passed in results:
        print(f"  [{'PASS' if passed else 'FAIL'}] {name}: {value}")
    live = compose(["ps", "-q"], ACTIVE["project"], capture=True, check=False).stdout.split()
    print(f"  {ACTIVE['name']} containers still present: {len(live)}")
    print(f"  backup size {(folder / 'db.dump').stat().st_size / 1e6:.1f} MB database; whole drill took {seconds:.0f} s")
    print("RESTORE DRILL: " + ("PASSED" if ok else "FAILED"))
    return 0 if ok else 1


def cmd_restore(a):
    folder = pathlib.Path(a.backup)
    folder = folder if folder.is_absolute() else ROOT / folder
    problems = verify_sums(folder)
    if problems:
        print("The backup is damaged. Nothing was changed:", "; ".join(problems))
        return 1
    word = "RESTORE-" + ACTIVE["name"].upper()
    print(f"This will REPLACE the {ACTIVE['name'].upper()} database and uploaded files with the backup in:\n    {folder}")
    if input(f"Type {word} to continue: ").strip() != word:
        print("Cancelled. Nothing was changed.")
        return 1
    if not a.no_safety_backup:
        print("First, a safety backup of the current state ...")
        make_backup(ACTIVE["out"], keep=0)   # the safety backup is local; a missing off-machine copy does not stop a restore
    project = ACTIVE["project"]
    compose(["up", "-d", "db"])
    wait_healthy("db", project)
    compose(["stop", "backend"])
    restore_dump(project, folder)
    compose(["up", "-d", "backend"])
    wait_healthy("backend", project)
    restore_uploads(project, folder)
    out = compose(["exec", "-T", "backend", "python", "scripts/verify_db_constraints.py"], project, capture=True, check=False)
    print(out.stdout.strip().splitlines()[-1] if out.stdout.strip() else "(no verification output)")
    print("Restored. Sign in and check the data before announcing it.")
    return 0 if out.returncode == 0 else 1


# ------------------------------------------------------------------------------------------------ schedule
def run_backup_cmd_text(root, python, copy_to=None, purge=True):
    """The batch file the scheduled task runs. It waits up to 10 minutes for Docker and retries twice, and writes to scheduled_run.log."""
    extra = f' --copy-to "{copy_to}"' if copy_to else ""
    purge_arg = " --purge" if purge else ""
    return (f'@echo off\r\ncd /d "{root}"\r\n'
            f'"{python}" scripts\\prod_ops.py backup{extra}{purge_arg} --wait-docker 10 --retries 2 --retry-wait 5 '
            f'>> backups\\prod\\{SCHEDULED_LOG} 2>&1\r\n')


def task_settings_ps(name="CDR-Backup"):
    """PowerShell that gives the task the settings a laptop or desktop needs for a 02:00 job."""
    return (f"$s = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -WakeToRun "
            f"-RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 10) -ExecutionTimeLimit (New-TimeSpan -Hours 2) -MultipleInstances IgnoreNew; "
            f"Set-ScheduledTask -TaskName '{name}' -Settings $s | Out-Null")


def cmd_schedule(a):
    if ACTIVE["name"] != "production":
        print("Scheduling is for production only. Staging is disposable and has no scheduled backup.")
        return 2
    if os.name != "nt":
        print("Add this line with `crontab -e` (daily at 02:00):")
        print(f"  0 2 * * * cd {ROOT} && {sys.executable} scripts/prod_ops.py backup --copy-to <off-machine folder> --purge --wait-docker 10 --retries 2 >> backups/prod/{SCHEDULED_LOG} 2>&1")
        print("And watch it from your monitoring with:  python scripts/prod_ops.py status   (exit code 1 = no recent backup)")
        return 0
    if a.remove:
        return subprocess.run(["schtasks", "/Delete", "/TN", "CDR-Backup", "/F"]).returncode
    out = ROOT / "backups" / "prod"
    out.mkdir(parents=True, exist_ok=True)
    cmd_file = out / "run_backup.cmd"
    cmd_file.write_text(run_backup_cmd_text(ROOT, sys.executable, a.copy_to, not a.no_purge), encoding="utf-8")
    r = subprocess.run(["schtasks", "/Create", "/SC", "DAILY", "/ST", a.time, "/TN", "CDR-Backup", "/TR", f'"{cmd_file}"', "/F"])
    if r.returncode == 0:
        r2 = subprocess.run(["powershell", "-NoProfile", "-Command", task_settings_ps()])
        if r2.returncode != 0:
            print("WARNING: the task was created, but its power settings could not be applied. In Task Scheduler open CDR-Backup, tab Conditions and "
                  "Settings: allow start on battery, do not stop on battery, run as soon as possible after a missed start, wake the computer.")
        print(f"Scheduled: every day at {a.time}. The task starts on battery, wakes the computer, runs after a missed start, waits up to 10 minutes "
              "for Docker Desktop (and starts it if needed) and tries again twice. It runs while you are signed in to Windows.")
        print(f"Its messages go to backups\\prod\\{SCHEDULED_LOG}. Check later with:  python scripts/prod_ops.py status")
    return r.returncode


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stack", choices=sorted(STACKS), default="production", help="production (the default) or staging, the rehearsal copy")
    common = argparse.ArgumentParser(add_help=False)          # the same option after the command name; absent there means "as given before it"
    common.add_argument("--stack", choices=sorted(STACKS), default=argparse.SUPPRESS)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("backup", parents=[common]); b.add_argument("--out", default=None); b.add_argument("--keep", type=int, default=14); b.add_argument("--copy-to"); b.add_argument("--purge", action="store_true", help="after the backup, remove expired refresh tokens and old notifications")
    b.add_argument("--wait-docker", type=float, default=0, metavar="MINUTES", help="wait (and start Docker Desktop on Windows) up to this long for Docker")
    b.add_argument("--retries", type=int, default=0, help="extra attempts when the backup fails")
    b.add_argument("--retry-wait", type=float, default=5, metavar="MINUTES", help="pause between attempts")
    s = sub.add_parser("status", parents=[common]); s.add_argument("--out", default=None); s.add_argument("--max-age-hours", type=float, default=26)
    sub.add_parser("check", parents=[common])
    pg = sub.add_parser("purge", parents=[common]); pg.add_argument("--apply", action="store_true")
    d = sub.add_parser("drill", parents=[common]); d.add_argument("--backup"); d.add_argument("--keep-drill", action="store_true")
    r = sub.add_parser("restore", parents=[common]); r.add_argument("backup"); r.add_argument("--no-safety-backup", action="store_true")
    c = sub.add_parser("schedule", parents=[common]); c.add_argument("--time", default="02:00"); c.add_argument("--remove", action="store_true"); c.add_argument("--copy-to"); c.add_argument("--no-purge", action="store_true", help="schedule the backup only, without housekeeping")
    a = ap.parse_args()
    use_stack(a.stack)
    if getattr(a, "out", 1) is None:
        a.out = ACTIVE["out"]
    if not (ROOT / ACTIVE["env"]).is_file() and a.cmd in ("backup", "check", "drill", "restore", "purge"):
        hint = "scripts/prod_setup.py --stack staging" if a.stack == "staging" else "scripts/prod_setup.py"
        print(f"{ACTIVE['env']} not found. This stack is not set up here ({hint}).")
        return 2
    try:
        return {"backup": cmd_backup, "status": cmd_status, "check": cmd_check, "purge": cmd_purge, "drill": cmd_drill, "restore": cmd_restore, "schedule": cmd_schedule}[a.cmd](a)
    except Fail as exc:
        print("FAILED:", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
