#!/usr/bin/env python3
"""
Backup, status, restore drill, restore and scheduling for the PRODUCTION stack (docker-compose.prod.yml).

    python scripts/prod_ops.py backup  [--out backups/prod] [--keep 14] [--copy-to <folder>]
    python scripts/prod_ops.py status  [--out backups/prod] [--max-age-hours 26]
    python scripts/prod_ops.py drill   [--backup <folder>] [--keep-drill]
    python scripts/prod_ops.py restore <backup folder>            (DESTRUCTIVE - replaces production data)
    python scripts/prod_ops.py schedule [--time 02:00] [--remove]  (Windows Task Scheduler; prints a cron line elsewhere)

Needs only Python 3 and Docker. A backup holds the database dump and the uploaded files from the same moment,
with SHA256SUMS and a MANIFEST (same layout as scripts/backup.ps1, so either restore script can read it).

THE DRILL restores a backup into a throw-away copy of the stack (its own project name, cdr-drill, its own volumes,
no published ports), checks it, and removes it. It never touches production: every command it runs names the
project cdr-drill, and the one destructive command (down -v) refuses to run for any other project.
"""
import argparse
import datetime
import hashlib
import os
import pathlib
import re
import shutil
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
PROD, DRILL = "cdr-prod", "cdr-drill"
STAMP = re.compile(r"^\d{8}T\d{6}Z$")
SLEEP = float(os.environ.get("CDR_OPS_SLEEP", "5"))
ROLE_SQL, BARE_ROLE_SQL = "database/roles/create_app_role.sql", "database/roles/create_bare_role.sql"
EXPECTED_PRIVILEGES = "f|t|t|f"   # cdr_app: no UPDATE on audit_logs, INSERT yes; UPDATE yes and DELETE no on submissions


class Fail(Exception):
    pass


def compose(args, project=PROD, capture=False, check=True):
    cmd = ["docker", "compose", "-p", project, "-f", "docker-compose.prod.yml", "--env-file", ".env.production", *args]
    r = subprocess.run(cmd, cwd=ROOT, capture_output=capture, text=True)
    if check and r.returncode != 0:
        tail = (r.stderr or "").strip()[-300:] if capture else ""
        raise Fail(f"docker compose {' '.join(args[:3])} ... failed (exit {r.returncode}) {tail}".strip())
    return r


def sh_in(service, script, project=PROD, capture=False):
    return compose(["exec", "-T", service, "sh", "-c", script], project, capture=capture)


def wait_healthy(service, project, tries=60):
    for _ in range(tries):
        cid = compose(["ps", "-q", service], project, capture=True, check=False).stdout.strip()
        if cid:
            st = subprocess.run(["docker", "inspect", "--format", "{{.State.Health.Status}}", cid], capture_output=True, text=True).stdout.strip()
            if st == "healthy":
                return
        time.sleep(SLEEP)
    raise Fail(f"{service} ({project}) did not become healthy")


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
    compose(["cp", str(pathlib.Path(folder) / "uploads.tar"), "backend:/tmp/uploads.tar"], project)
    sh_in("backend", "rm -rf /app/uploads/* && tar -C /app -xf /tmp/uploads.tar && chown -R cdr:cdr /app/uploads && rm -f /tmp/uploads.tar", project)


# ------------------------------------------------------------------------------------------------ backup
def make_backup(out_dir, keep, copy_to=None):
    out_dir = pathlib.Path(out_dir)
    out_dir = out_dir if out_dir.is_absolute() else ROOT / out_dir
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    folder = out_dir / stamp
    folder.mkdir(parents=True, exist_ok=True)
    print(f"Backing up production to {folder} ...")
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
    manifest = ["CDR backup (production)", f"taken (UTC):     {stamp}", f"schema revision: {revision}", "files:"]
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
    with open(out_dir / "backup.log", "a", encoding="utf-8") as log:
        log.write(f"{stamp} {'COPY-FAILED' if copy_error else 'OK'} {folder.name} revision={revision}\n")
    print("Done (local backup OK)." if copy_error else "Done.")
    return folder, copy_error


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


def cmd_backup(a):
    _, copy_error = make_backup(a.out, a.keep, a.copy_to)
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
    assert project == DRILL and project != PROD, "refusing to remove anything but the drill project"
    compose(["down", "-v", "--remove-orphans"], project, check=False)


def cmd_drill(a):
    folder = pathlib.Path(a.backup) if a.backup else newest_backup("backups/prod")
    if folder is None:
        print("No backup to test. Take one first: python scripts/prod_ops.py backup (or give --backup <folder>).")
        return 2
    folder = folder if folder.is_absolute() else ROOT / folder
    problems = verify_sums(folder)
    if problems:
        print("The backup is damaged, so the drill stops here:", "; ".join(problems))
        return 1
    print(f"RESTORE DRILL of {folder.name} into a throw-away copy (project {DRILL}). Production is not touched.")
    started = time.time()
    results, ok = [], True
    try:
        compose(["up", "-d", "db"], DRILL)
        wait_healthy("db", DRILL)
        restore_dump(DRILL, folder)
        compose(["up", "-d", "backend"], DRILL)
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
            print(f"The drill stack was left running (project {DRILL}). Remove it with: docker compose -p {DRILL} -f docker-compose.prod.yml --env-file .env.production down -v")
        else:
            teardown_drill()
    seconds = time.time() - started
    for name, value, passed in results:
        print(f"  [{'PASS' if passed else 'FAIL'}] {name}: {value}")
    prod = compose(["ps", "-q"], PROD, capture=True, check=False).stdout.split()
    print(f"  production containers still present: {len(prod)}")
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
    print(f"This will REPLACE the PRODUCTION database and uploaded files with the backup in:\n    {folder}")
    if input("Type RESTORE-PRODUCTION to continue: ").strip() != "RESTORE-PRODUCTION":
        print("Cancelled. Nothing was changed.")
        return 1
    if not a.no_safety_backup:
        print("First, a safety backup of the current state ...")
        make_backup("backups/prod", keep=0)   # the safety backup is local; a missing off-machine copy does not stop a restore
    compose(["up", "-d", "db"])
    wait_healthy("db", PROD)
    compose(["stop", "backend"])
    restore_dump(PROD, folder)
    compose(["up", "-d", "backend"])
    wait_healthy("backend", PROD)
    restore_uploads(PROD, folder)
    out = compose(["exec", "-T", "backend", "python", "scripts/verify_db_constraints.py"], PROD, capture=True, check=False)
    print(out.stdout.strip().splitlines()[-1] if out.stdout.strip() else "(no verification output)")
    print("Restored. Sign in and check the data before announcing it.")
    return 0 if out.returncode == 0 else 1


# ------------------------------------------------------------------------------------------------ schedule
def cmd_schedule(a):
    if os.name != "nt":
        print("Add this line with `crontab -e` (daily at 02:00):")
        print(f"  0 2 * * * cd {ROOT} && {sys.executable} scripts/prod_ops.py backup --copy-to <off-machine folder> >> backups/prod/backup.log 2>&1")
        print("And watch it from your monitoring with:  python scripts/prod_ops.py status   (exit code 1 = no recent backup)")
        return 0
    if a.remove:
        return subprocess.run(["schtasks", "/Delete", "/TN", "CDR-Backup", "/F"]).returncode
    out = ROOT / "backups" / "prod"
    out.mkdir(parents=True, exist_ok=True)
    cmd_file = out / "run_backup.cmd"
    extra = f' --copy-to "{a.copy_to}"' if a.copy_to else ""
    cmd_file.write_text(f'@echo off\r\ncd /d "{ROOT}"\r\n"{sys.executable}" scripts\\prod_ops.py backup{extra} >> backups\\prod\\backup.log 2>&1\r\n', encoding="utf-8")
    r = subprocess.run(["schtasks", "/Create", "/SC", "DAILY", "/ST", a.time, "/TN", "CDR-Backup", "/TR", f'"{cmd_file}"', "/F"])
    if r.returncode == 0:
        print(f"Scheduled: every day at {a.time}. It runs only while you are signed in to Windows and Docker Desktop is running.")
        print("Check later with:  python scripts/prod_ops.py status")
    return r.returncode


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("backup"); b.add_argument("--out", default="backups/prod"); b.add_argument("--keep", type=int, default=14); b.add_argument("--copy-to")
    s = sub.add_parser("status"); s.add_argument("--out", default="backups/prod"); s.add_argument("--max-age-hours", type=float, default=26)
    d = sub.add_parser("drill"); d.add_argument("--backup"); d.add_argument("--keep-drill", action="store_true")
    r = sub.add_parser("restore"); r.add_argument("backup"); r.add_argument("--no-safety-backup", action="store_true")
    c = sub.add_parser("schedule"); c.add_argument("--time", default="02:00"); c.add_argument("--remove", action="store_true"); c.add_argument("--copy-to")
    a = ap.parse_args()
    if not (ROOT / ".env.production").is_file() and a.cmd in ("backup", "drill", "restore"):
        print(".env.production not found. This tool is for the production stack (scripts/prod_setup.py).")
        return 2
    try:
        return {"backup": cmd_backup, "status": cmd_status, "drill": cmd_drill, "restore": cmd_restore, "schedule": cmd_schedule}[a.cmd](a)
    except Fail as exc:
        print("FAILED:", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
