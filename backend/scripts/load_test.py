#!/usr/bin/env python3
"""
Load test for the STAGING stack (see docs/LOAD_TESTING.md). It runs INSIDE the staging backend container and goes through the staging web server,
so the whole path is measured (nginx, the application, the database). It refuses to run anywhere else.

    docker compose -p cdr-staging -f docker-compose.prod.yml --env-file .env.staging exec -u cdr backend python scripts/load_test.py setup
    docker compose -p cdr-staging -f docker-compose.prod.yml --env-file .env.staging exec -u cdr backend python scripts/load_test.py run

setup  creates synthetic institutions, one user for each, and a BOT analyst (the staging administrator's password is typed at a hidden prompt, or
       read from CDR_ADMIN_PASSWORD). Everything it creates is named lt_... / LT...; staging is disposable: erase it with `down -v` (docs/STAGING.md).
run    signs everybody in, each institution uploads a file of synthetic loans, the analyst approves them, then several people read the dashboards at
       once for a while (and, if asked, one very large file is uploaded). It prints how long things took and whether they met the targets.

Uses the standard library only. All data is synthetic.
"""
import argparse
import getpass
import http.client
import json
import math
import os
import random
import secrets
import ssl
import sys
import threading
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

def default_dir(uploads=Path("/app/uploads")):
    """Where the synthetic users' passwords and the results are kept: in the staging uploads volume, so they SURVIVE the backend container being
    recreated (every staging_up recreates it; /tmp would be lost). Staging only holds synthetic data; `down -v` erases it all. /tmp elsewhere."""
    return uploads / "_loadtest" if uploads.is_dir() and os.access(uploads, os.W_OK) else Path("/tmp")


OUT_DIR = Path(os.environ.get("CDR_LOADTEST_DIR") or default_dir())


def not_set_up_message(out_dir=None, uploads=Path("/app/uploads")) -> str:
    """The message when the saved accounts are not found. When the tool fell back to /tmp although the uploads volume exists, the real cause is nearly always
    that it was started as root: the container no longer lets root write into the application's own volume (docs/DOCKER.md), so it has to be run as that user."""
    text = "Not set up yet. Run: python scripts/load_test.py setup"
    if Path(out_dir if out_dir is not None else OUT_DIR) == Path("/tmp") and Path(uploads).is_dir():
        text += ("\n(The saved accounts live in the uploads volume, which only the application's own user may write now that the container's privileges are limited, so "
                 "this run looked in /tmp instead. If you ran 'setup' before, run the tool as that user: add  -u cdr  after 'exec', for example\n"
                 "docker compose ... exec -u cdr backend python scripts/load_test.py run ...)")
    return text
CREDENTIALS = OUT_DIR / "loadtest_users.json"
RESULTS = OUT_DIR / "loadtest_results.json"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
SHEET = "Loan_Collateral_Data"


# ------------------------------------------------------------------ safety: never against production
def require_staging():
    """The tool runs only where CDR_ALLOW_LOAD_TEST is exactly "yes": .env.staging sets it, .env.production must not (the checker refuses it)."""
    if os.environ.get("CDR_ALLOW_LOAD_TEST") != "yes":
        raise SystemExit("REFUSED: this load test runs only in the staging stack (CDR_ALLOW_LOAD_TEST=yes). It must never run against production.\n"
                         "Use:  docker compose -p cdr-staging -f docker-compose.prod.yml --env-file .env.staging exec -u cdr backend python scripts/load_test.py ...")


# ------------------------------------------------------------------ numbers
def percentile(sorted_values, p):
    """Nearest-rank percentile of an already sorted list (0 for an empty list)."""
    if not sorted_values:
        return 0.0
    return sorted_values[max(1, math.ceil(p / 100 * len(sorted_values))) - 1]


def summarise(samples, elapsed):
    """samples: [(ok, seconds)]. Times are reported in milliseconds."""
    times = sorted(s * 1000 for _, s in samples)
    n = len(samples)
    errors = sum(1 for ok, _ in samples if not ok)
    return {
        "requests": n, "errors": errors, "error_rate": (errors / n) if n else 0.0, "per_second": (n / elapsed) if elapsed > 0 else 0.0,
        "min_ms": times[0] if times else 0.0, "mean_ms": (sum(times) / n) if n else 0.0, "p50_ms": percentile(times, 50),
        "p95_ms": percentile(times, 95), "p99_ms": percentile(times, 99), "max_ms": times[-1] if times else 0.0,
    }


class Recorder:
    def __init__(self):
        self._lock = threading.Lock()
        self.samples = {}
        self.errors = {}

    def add(self, scenario, ok, seconds, error=None):
        with self._lock:
            self.samples.setdefault(scenario, []).append((ok, seconds))
            if error:
                seen = self.errors.setdefault(scenario, {})
                seen[error] = seen.get(error, 0) + 1

    def summary(self, scenario, elapsed):
        out = summarise(self.samples.get(scenario, []), elapsed)
        out["error_samples"] = sorted(self.errors.get(scenario, {}).items(), key=lambda kv: -kv[1])[:3]
        return out


# ------------------------------------------------------------------ synthetic data
def strong_password():
    """Meets the password policy (letters, a digit, a special character, 17 characters, so it also meets the stricter rule for the Bank's staff) and is random."""
    return "Lt" + secrets.token_hex(6) + "#" + str(secrets.randbelow(90) + 10)


def make_rows(count, tag, seed=None):
    """Synthetic loans with real region and district pairs and unique loan numbers; amounts the database accepts."""
    from app.services import geo_lookup
    rnd = random.Random(seed)
    regions = geo_lookup.all_regions()
    rows = []
    for i in range(count):
        region = rnd.choice(regions)
        loan = rnd.randint(1, 500) * 1_000_000
        rows.append({
            "customer_id": f"CUST-{tag}-{i:07d}", "loan_id": f"LN-{tag}-{i:07d}", "loan_amount_tzs": loan,
            "outstanding_principal_tzs": int(loan * rnd.uniform(0.2, 1.0)), "annual_interest_rate": round(rnd.uniform(5, 25), 2),
            "collateral_type": "Residential mortgage", "collateral_value_tzs": int(loan * rnd.uniform(1.0, 1.6)),
            "region": region, "district": rnd.choice(geo_lookup.districts_for_region(region) or [None]),
        })
    return rows


def build_workbook(rows):
    """The official template's layout (header labels in BOT's wording), written row by row so a very large file does not need much memory."""
    import io
    from openpyxl import Workbook
    from app.services.template_generator import COLUMNS
    labels = dict(COLUMNS)
    fields = [f for f, _ in COLUMNS]
    wb = Workbook(write_only=True)
    ws = wb.create_sheet(SHEET)
    ws.append([labels[f] for f in fields])
    for row in rows:
        ws.append([row.get(f) for f in fields])
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


# ------------------------------------------------------------------ a small HTTP client (standard library, keeps its connection)
def encode_multipart(fields, files):
    boundary = "----cdrloadtest" + secrets.token_hex(8)
    parts = []
    for name, value in fields.items():
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
    for name, (filename, data, ctype) in files.items():
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; filename="{filename}"\r\nContent-Type: {ctype}\r\n\r\n'.encode() + data + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


class Http:
    def __init__(self, base, insecure=False):
        u = urllib.parse.urlsplit(base)
        self.https = u.scheme == "https"
        self.host, self.port = u.hostname, u.port or (443 if self.https else 80)
        self.context = (ssl._create_unverified_context() if insecure else ssl.create_default_context()) if self.https else None
        self.conn = None

    def _connect(self):
        if self.https:
            return http.client.HTTPSConnection(self.host, self.port, context=self.context, timeout=600)
        return http.client.HTTPConnection(self.host, self.port, timeout=600)

    def close(self):
        if self.conn:
            try:
                self.conn.close()
            finally:
                self.conn = None

    def request(self, method, path, token=None, json_body=None, form=None, files=None):
        """(status, parsed JSON or None, seconds). A kept-alive connection the server has dropped is replaced once."""
        headers, body = {"Accept": "application/json"}, None
        if json_body is not None:
            body, headers["Content-Type"] = json.dumps(json_body).encode(), "application/json"
        elif files:
            body, headers["Content-Type"] = encode_multipart(form or {}, files)
        if token:
            headers["Authorization"] = f"Bearer {token}"
        started = time.perf_counter()
        for attempt in (1, 2):
            reused = self.conn is not None
            try:
                self.conn = self.conn or self._connect()
                self.conn.request(method, path, body=body, headers=headers)
                response = self.conn.getresponse()
                data = response.read()
                if response.will_close:
                    self.close()
                break
            except (http.client.RemoteDisconnected, ConnectionResetError, BrokenPipeError):
                self.close()
                if attempt == 2 or not reused:
                    raise
        seconds = time.perf_counter() - started
        try:
            payload = json.loads(data) if data else None
        except ValueError:
            payload = None
        return response.status, payload, seconds


def login(http_client, username, password):
    status, payload, seconds = http_client.request("POST", "/api/auth/login", json_body={"username": username, "password": password})
    if status == 200 and isinstance(payload, dict) and payload.get("access_token"):
        return payload["access_token"], seconds
    if isinstance(payload, dict) and (payload.get("mfa_required") or payload.get("mfa_setup_required")):
        raise SystemExit(f"{username} is asked for two-step sign-in. Staging has MFA_REQUIRED=false by default; set it back to false in .env.staging for a load test.")
    raise SystemExit(f"Sign-in of {username} failed (HTTP {status}): {(payload or {}).get('detail') if isinstance(payload, dict) else payload}")


def check_reachable(base, insecure):
    probe = Http(base, insecure)
    try:
        status, _, _ = probe.request("GET", "/api/health")
    except OSError as exc:
        raise SystemExit(f"Cannot reach the staging web server at {base} ({type(exc).__name__}). Is staging up? (scripts/staging_up.ps1)")
    finally:
        probe.close()
    if status != 200:
        raise SystemExit(f"The staging web server did not answer the health check (HTTP {status}) at {base}.")


def detail(payload):
    return str(payload.get("detail"))[:120] if isinstance(payload, dict) and payload.get("detail") else None


# ------------------------------------------------------------------ setup
def cmd_setup(args):
    require_staging()
    if CREDENTIALS.exists() and not args.again:
        print(f"Already set up ({CREDENTIALS}). Use --again to create a new set.")
        return 0
    check_reachable(args.base, args.insecure)
    password = os.environ.get("CDR_ADMIN_PASSWORD") or getpass.getpass(f"Password of {args.admin}: ")
    from app.core.timeutil import utcnow
    suffix = utcnow().strftime("%y%m%d%H%M")
    client = Http(args.base, args.insecure)
    token, _ = login(client, args.admin, password)

    def create(path, body):
        status, payload, _ = client.request("POST", path, token=token, json_body=body)
        if status not in (200, 201):
            raise SystemExit(f"POST {path} failed (HTTP {status}): {detail(payload)}")
        return payload

    users = []
    for n in range(1, args.institutions + 1):
        institution = create("/api/institutions", {"code": f"LT{suffix}{n:02d}", "name": f"Load Test Bank {suffix}-{n:02d}"})
        username, pw = f"lt_{suffix}_{n:02d}", strong_password()
        create("/api/users", {"full_name": f"Load Test User {n:02d}", "username": username, "email": f"{username}@example.com", "password": pw,
                              "role": "INSTITUTION_USER", "institution_id": institution["id"]})
        users.append({"username": username, "password": pw, "institution_code": institution["code"]})
    analyst = {"username": f"lt_{suffix}_analyst", "password": strong_password()}
    create("/api/users", {"full_name": "Load Test Analyst", "username": analyst["username"], "email": f"{analyst['username']}@example.com",
                          "password": analyst["password"], "role": "BOT_USER"})
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    CREDENTIALS.write_text(json.dumps({"suffix": suffix, "institution_users": users, "analyst": analyst}, indent=1), encoding="utf-8")
    try:
        CREDENTIALS.chmod(0o600)
    except OSError:
        pass
    print(f"Created {len(users)} synthetic institutions with one user each, and one analyst. Credentials: {CREDENTIALS} (inside this container only).")
    return 0


# ------------------------------------------------------------------ run
READS_ANALYST = [("kpi_summary", "/api/analytics/kpi-summary", 4), ("hazard_exposure", "/api/analytics/hazard-exposure", 2),
                 ("combined_exposure", "/api/analytics/combined-climate-financial-exposure", 2), ("map_points", "/api/analytics/map-points", 2),
                 ("exposure_points", "/api/analytics/exposure-points", 1), ("submissions", "/api/submissions", 3),
                 ("institutions", "/api/institutions", 1), ("risk_advisories", "/api/risk-advisories", 1), ("me", "/api/auth/me", 1)]
READS_INSTITUTION = [("kpi_summary", "/api/analytics/kpi-summary", 3), ("submissions", "/api/submissions", 3), ("me", "/api/auth/me", 1)]


def read_loop(base, insecure, token, reads, deadline, recorder, seed, scenario="read", stop=None):
    """One person reading pages until the deadline (or until `stop` is set), under the scenario name given."""
    rnd, client = random.Random(seed), Http(base, insecure)
    names, paths, weights = [r[0] for r in reads], {r[0]: r[1] for r in reads}, [r[2] for r in reads]
    try:
        while time.monotonic() < deadline and not (stop is not None and stop.is_set()):
            name = rnd.choices(names, weights)[0]
            try:
                status, payload, seconds = client.request("GET", paths[name], token=token)
                ok = 200 <= status < 300
                error = None if ok else f"{name}: HTTP {status} {detail(payload) or ''}".strip()
            except Exception as exc:                     # a refused or dropped connection is a result, not a crash
                client.close()
                ok, seconds, error = False, 0.0, f"{name}: {type(exc).__name__}"
            recorder.add(scenario, ok, seconds, error)
            recorder.add(f"{scenario}:{name}", ok, seconds)
            time.sleep(rnd.uniform(0.05, 0.3))
    finally:
        client.close()


def run_readers(args, base, insecure, tokens, analyst, insts, recorder, scenario, duration=None, stop=None):
    """`args.users` people read the dashboards (70% analysts) for `duration` seconds, or until `stop` is set. Returns how many seconds it took."""
    deadline = time.monotonic() + (duration if duration is not None else 3600)
    started = time.monotonic()
    analysts = max(1, round(args.users * 0.7))
    with ThreadPoolExecutor(max_workers=args.users) as pool:
        for k in range(args.users):
            if k < analysts:
                token, reads = tokens[analyst["username"]], READS_ANALYST
            else:
                token, reads = tokens[insts[k % len(insts)]["username"]], READS_INSTITUTION
            pool.submit(read_loop, base, insecure, token, reads, deadline, recorder, k, scenario, stop)
    return time.monotonic() - started


def container_memory(base="/sys/fs/cgroup"):
    """Memory of THIS container (the backend; the load-test tool runs in it too, so its own use is included). None where the system does not say."""
    base = Path(base)

    def first(*names):
        for name in names:
            try:
                value = (base / name).read_text().strip()
                return None if value == "max" else int(value)
            except (OSError, ValueError):
                continue
        return None
    limit = first("memory.max", "memory/memory.limit_in_bytes")
    return {"current": first("memory.current", "memory/memory.usage_in_bytes"), "peak": first("memory.peak", "memory/memory.max_usage_in_bytes"),
            "limit": limit if limit is None or limit < 1 << 60 else None}


def timed(recorder, scenario, client, *args, **kwargs):
    try:
        status, payload, seconds = client.request(*args, **kwargs)
    except Exception as exc:
        client.close()
        recorder.add(scenario, False, 0.0, type(exc).__name__)
        return None, None
    ok = 200 <= status < 300
    recorder.add(scenario, ok, seconds, None if ok else f"HTTP {status} {detail(payload) or ''}".strip())
    return status, payload


def upload(recorder, scenario, base, insecure, token, period, workbook, name):
    client = Http(base, insecure)
    try:
        status, payload = timed(recorder, scenario, client, "POST", "/api/submissions/upload", token=token, form={"reporting_period": period},
                                files={"file": (name, workbook, XLSX)})
    finally:
        client.close()
    if isinstance(payload, dict) and payload.get("status") not in (None, "VALID"):
        # The file was received but judged invalid: the generator, not the system, is wrong. Say so loudly.
        recorder.add(f"{scenario}:not_valid", False, 0.0, f"the file was judged {payload.get('status')}: {payload.get('invalid_records')} invalid record(s)")
    return payload if isinstance(payload, dict) else None


def cmd_run(args):
    require_staging()
    if not CREDENTIALS.exists():
        raise SystemExit(not_set_up_message())
    creds = json.loads(CREDENTIALS.read_text(encoding="utf-8"))
    insts, analyst = creds["institution_users"], creds["analyst"]
    recorder, base, insecure = Recorder(), args.base, args.insecure
    check_reachable(base, insecure)
    print(f"LOAD TEST of STAGING at {base}: {len(insts)} institution users, 1 analyst, {args.rows} loans per file, {args.users} readers for {args.duration}s")
    results, tokens = {}, {}

    # 1. everybody signs in at once
    def sign_in(who):
        client = Http(base, insecure)
        try:
            token, seconds = login(client, who["username"], who["password"])
            recorder.add("signin", True, seconds)
            tokens[who["username"]] = token
        finally:
            client.close()
    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=len(insts) + 1) as pool:
        list(pool.map(sign_in, insts + [analyst]))
    results["signin"] = recorder.summary("signin", time.monotonic() - started)

    # 2. every institution uploads a file (the files are built first, so building them is not counted)
    period = args.period
    books = [build_workbook(make_rows(args.rows, f"{creds['suffix']}-{n:02d}", seed=n)) for n in range(1, len(insts) + 1)]
    print(f"  upload: {len(books)} files of {args.rows} loans ({len(books[0]) / 1e6:.1f} MB each) ...")
    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=len(insts)) as pool:
        replies = list(pool.map(lambda i: upload(recorder, "upload", base, insecure, tokens[insts[i]["username"]], period, books[i], f"load_{i + 1}.xlsx"), range(len(insts))))
    results["upload"] = recorder.summary("upload", time.monotonic() - started)
    if recorder.samples.get("upload:not_valid"):
        results["upload_not_valid"] = recorder.summary("upload:not_valid", 1)

    # 3. the analyst approves what was uploaded
    submissions = [r["id"] for r in replies if r and r.get("id") and r.get("status") == "VALID"]
    started = time.monotonic()

    def approve(sid):
        client = Http(base, insecure)
        try:
            timed(recorder, "review", client, "POST", f"/api/submissions/{sid}/review", token=tokens[analyst["username"]], json_body={"decision": "APPROVE"})
        finally:
            client.close()
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(approve, submissions))
    results["review"] = recorder.summary("review", time.monotonic() - started)

    # 4. many people read the dashboards at once
    print(f"  reading: {args.users} people for {args.duration} seconds ...")
    elapsed = run_readers(args, base, insecure, tokens, analyst, insts, recorder, "read", duration=args.duration)
    results["read"] = recorder.summary("read", elapsed)
    for name in sorted(n for n in recorder.samples if n.startswith("read:")):
        results[name] = recorder.summary(name, elapsed)

    # 5. optionally one very large file; with --mixed people keep reading while it is being checked; then it is approved and read at its size
    if args.big_rows:
        print(f"  one large file of {args.big_rows} loans" + (", while people keep reading" if args.mixed else "") + " ...")
        big = build_workbook(make_rows(args.big_rows, f"{creds['suffix']}-BIG", seed=99))
        big_token, holder = tokens[insts[0]["username"]], {}
        started = time.monotonic()
        if args.mixed:
            stop = threading.Event()

            def big_upload():
                try:
                    holder["reply"] = upload(recorder, "upload_big", base, insecure, big_token, args.big_period, big, "load_big.xlsx")
                finally:
                    stop.set()
            worker = threading.Thread(target=big_upload)
            worker.start()
            read_elapsed = run_readers(args, base, insecure, tokens, analyst, insts, recorder, "read_during_upload", stop=stop)
            worker.join()
            results["read_during_upload"] = recorder.summary("read_during_upload", read_elapsed)
        else:
            holder["reply"] = upload(recorder, "upload_big", base, insecure, big_token, args.big_period, big, "load_big.xlsx")
        results["upload_big"] = recorder.summary("upload_big", time.monotonic() - started)
        reply = holder.get("reply") or {}
        print(f"    the large file: status {reply.get('status')}, {reply.get('valid_records')} valid record(s), {results['upload_big']['p50_ms'] / 1000:.0f} s")
        for key in [k for k in recorder.samples if k.endswith(":not_valid")]:
            results[key.replace(":", "_")] = recorder.summary(key, 1)
        if reply.get("id") and reply.get("status") == "VALID":
            client = Http(base, insecure)
            try:
                timed(recorder, "review_big", client, "POST", f"/api/submissions/{reply['id']}/review", token=tokens[analyst["username"]], json_body={"decision": "APPROVE"})
            finally:
                client.close()
            results["review_big"] = recorder.summary("review_big", 1)
            print(f"  reading again with the large file approved: {args.users} people for {args.duration} seconds ...")
            elapsed = run_readers(args, base, insecure, tokens, analyst, insts, recorder, "read_large", duration=args.duration)
            results["read_large"] = recorder.summary("read_large", elapsed)
    results["memory_bytes"] = container_memory()
    return report(results, args)


# ------------------------------------------------------------------ the verdict
def targets(args):
    return [("read", "p95_ms", args.slo_read_p95_ms), ("signin", "p95_ms", args.slo_signin_p95_ms), ("upload", "p95_ms", args.slo_upload_p95_ms),
            ("review", "p95_ms", args.slo_review_p95_ms), ("upload_big", "p95_ms", args.slo_upload_big_ms), ("review_big", "p95_ms", args.slo_review_big_ms),
            ("read_during_upload", "p95_ms", args.slo_read_during_upload_p95_ms), ("read_large", "p95_ms", args.slo_read_p95_ms)]


def report(results, args):
    print("\n%-26s %8s %7s %7s %9s %9s %9s %9s" % ("scenario", "requests", "errors", "req/s", "p50 ms", "p95 ms", "p99 ms", "max ms"))
    memory = results.pop("memory_bytes", None)
    for name, r in results.items():
        print("%-26s %8d %7d %7.1f %9.0f %9.0f %9.0f %9.0f" % (name, r["requests"], r["errors"], r["per_second"], r["p50_ms"], r["p95_ms"], r["p99_ms"], r["max_ms"]))
        for message, count in r.get("error_samples", []):
            print(f"      {count} x {message}")
    verdicts, failed = [], False
    for scenario, key, limit in targets(args):
        r = results.get(scenario)
        if not r or not r["requests"]:
            continue
        ok = r[key] <= limit and r["error_rate"] <= args.slo_error_rate
        failed |= not ok
        verdicts.append({"scenario": scenario, "measure": key, "limit": limit, "value": round(r[key], 1), "error_rate": round(r["error_rate"], 4), "pass": ok})
        print(f"  {'PASS' if ok else 'FAIL'}  {scenario}: {key} {r[key]:.0f} (limit {limit:g}), errors {r['error_rate'] * 100:.1f}% (limit {args.slo_error_rate * 100:g}%)")
    if any(k.endswith("_not_valid") and v["requests"] for k, v in results.items()):
        failed = True
        print("  FAIL  some generated files were judged invalid: the test data is wrong, so the upload figures mean nothing")
    import resource
    own = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    if memory is not None:
        memory["load_test_tool_peak_mb"] = round(own)
    if memory and memory.get("peak"):
        mb = lambda v: "no limit set" if v is None else f"{v / 1048576:.0f} MB"
        print(f"  memory of the backend container: peak {mb(memory['peak'])}, now {mb(memory['current'])}, limit {mb(memory['limit'])} (this includes the load-test tool itself, which runs in it and alone peaked at {own:.0f} MB, so the application's own share is at most about {max(0, memory['peak'] / 1048576 - own):.0f} MB)")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS.write_text(json.dumps({"finished_utc": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()), "settings": {k: v for k, v in vars(args).items() if k != "func"},
                                   "results": results, "memory_bytes": memory, "verdicts": verdicts}, indent=1, default=str), encoding="utf-8")
    print(f"\nResults saved: {RESULTS}   (copy out with: docker compose -p cdr-staging -f docker-compose.prod.yml --env-file .env.staging cp backend:{RESULTS} .)")
    print("The targets are PROPOSED starting points, to be agreed with the Bank (docs/LOAD_TESTING.md).")
    return 3 if failed else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)
    for name in ("setup", "run"):
        p = sub.add_parser(name)
        p.add_argument("--base", default="https://frontend", help="the staging web server as the backend container sees it")
        p.add_argument("--insecure", action="store_true", default=True, help="accept the staging self-signed certificate (the default; this tool only talks to staging)")
    s = sub.choices["setup"]
    s.add_argument("--admin", default="stagingadmin")
    s.add_argument("--institutions", type=int, default=8)
    s.add_argument("--again", action="store_true", help="create a new set even if one exists")
    s.set_defaults(func=cmd_setup)
    r = sub.choices["run"]
    r.add_argument("--rows", type=int, default=2000, help="loans in each institution's file")
    r.add_argument("--users", type=int, default=20, help="people reading the dashboards at the same time")
    r.add_argument("--duration", type=int, default=60, help="seconds of reading")
    r.add_argument("--period", default="2026-Q1")
    r.add_argument("--big-rows", type=int, default=0, help="also upload ONE file of this many loans (the largest allowed is 100000)")
    r.add_argument("--big-period", default="2026-Q2")
    r.add_argument("--mixed", action="store_true", help="with --big-rows: people keep reading dashboards while the large file is being checked")
    r.add_argument("--slo-upload-big-ms", type=float, default=120000)
    r.add_argument("--slo-review-big-ms", type=float, default=30000)
    r.add_argument("--slo-read-during-upload-p95-ms", type=float, default=3000)
    r.add_argument("--slo-read-p95-ms", type=float, default=1500)
    r.add_argument("--slo-signin-p95-ms", type=float, default=4000)
    r.add_argument("--slo-upload-p95-ms", type=float, default=30000)
    r.add_argument("--slo-review-p95-ms", type=float, default=5000)
    r.add_argument("--slo-error-rate", type=float, default=0.01)
    r.set_defaults(func=cmd_run)
    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
