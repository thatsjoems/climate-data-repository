# Load testing (staging only)

`backend/scripts/load_test.py` measures how the system behaves when many people use it at once, **on the staging stack, never on production**
(see `docs/STAGING.md`). It uses only synthetic data and the standard library.

## Why it cannot touch production (three safeguards)
1. It **refuses to run** unless the container says `CDR_ALLOW_LOAD_TEST=yes`. Only `.env.staging` sets it; production's backend does not have it.
2. The **production checker refuses** a `.env.production` that contains `CDR_ALLOW_LOAD_TEST` or that switches the rate limit off.
3. It is run with `-p cdr-staging ... exec backend`, so the command itself addresses the staging containers, and it goes through the **staging** web server.

## Before the first run
Staging must be up and have an administrator (`docs/STAGING.md`). Staging needs two settings that new staging files already contain
(`RATE_LIMIT_ENABLED=false`, `CDR_ALLOW_LOAD_TEST=yes`). **If your `.env.staging` was made before this guide, add them** and start staging again:
```
Add-Content .env.staging "RATE_LIMIT_ENABLED=false"
Add-Content .env.staging "CDR_ALLOW_LOAD_TEST=yes"
powershell -ExecutionPolicy Bypass -File .\scripts\staging_up.ps1
```
The rate limit is off in staging on purpose: with it on, a load test would measure the limit (10 sign-ins a minute, 200 requests a minute) and nothing else.
The limit itself is covered by tests (`test_rate_limit_real_address.py`).

## Run it
```
docker compose -p cdr-staging -f docker-compose.prod.yml --env-file .env.staging exec -u cdr backend python scripts/load_test.py setup
docker compose -p cdr-staging -f docker-compose.prod.yml --env-file .env.staging exec -u cdr backend python scripts/load_test.py run
```
`setup` asks for the staging administrator's password (hidden) and creates 8 synthetic institutions, one user each and one analyst (all named `lt_...`).
`run` then: signs everybody in at the same time; has every institution upload a file of synthetic loans (2,000 by default) at the same time; has the analyst approve them;
then has 20 people (70% analysts, 30% institution users) read the dashboards for 60 seconds; and prints a table of timings.

Useful options of `run`: `--rows 5000` (loans per file), `--users 40` (people reading), `--duration 120` (seconds), `--big-rows 100000` (also upload ONE file of the largest allowed size),
and `--mixed` (with `--big-rows`: people keep reading the dashboards **while** the large file is being checked).
With `--big-rows` the tool then **approves** the large file and has people read the dashboards **again at that size** (`read_large`), and it prints how much memory the backend container used.
While it runs you can also watch the machine in another window: `docker stats`.
A full test of the worst case: `... load_test.py run --big-rows 100000 --mixed` (about five minutes).

## Reading the result
For each scenario: how many requests, how many failed, requests per second, and the time in milliseconds (median `p50`, `p95` = 19 in 20 were faster, `p99`, `max`).
`read:<name>` rows break the reading down by page. A **FAIL** line says which target was missed. **If a line says the generated files were judged invalid, the test data is wrong and the upload figures mean nothing**:
tell the developer. The numbers are saved in `loadtest_results.json` in the staging uploads volume (the tool prints the exact path and the command to copy them out). The passwords of the synthetic users are kept there too, so they survive `staging_up`
recreating the backend; `down -v` erases them with everything else.

### The targets are proposals
| Measure | Proposed limit | Why |
|---|---|---|
| Reading a dashboard page, p95 | 1.5 s | a person waits, a slower page feels broken |
| Sign-in, p95 | 4 s | the password check is deliberately slow (bcrypt) |
| Uploading a 2,000-loan file, p95 | 30 s | the file is checked row by row |
| Approving a submission, p95 | 5 s | |
| Errors | at most 1% | |
| The largest file (100,000 loans), time to be checked | 120 s | the longest a person should wait; the web server allows these uploads 300 s |
| Reading while that file is being checked, p95 | 3 s | one bank's big file should not stall everyone |
| Approving that file, p95 | 30 s | |
**They are starting points, not requirements.** The Bank has not stated performance requirements; agreeing them is an open decision (TBD) for BOT.

## What a result does and does not tell you
* It tells you whether this code, on **this machine**, copes with the load you set, and where it slows down first.
* It is **not** a promise about production: the machine, the real data volume, real network distance and browsers rendering the pages are different. Staging and production share the same
  machine here, so run heavy tests when production is quiet.
* The rate limit is not exercised (it is off). A very large file (`--big-rows 100000`) shows how the application behaves at its upload limit; failing it is information, not necessarily a defect.
* The tool measures the server. How long a browser takes to draw the dashboard (it loads seven datasets) is not measured.
* Everything it creates stays in staging. To start clean: `docker compose -p cdr-staging -f docker-compose.prod.yml --env-file .env.staging down -v` (always with `-p cdr-staging`).

## What was verified
The tool was run end to end against a stand-in server that checked every token and opened every uploaded Excel file (official header, row counts, unique loan numbers, real region and district pairs, amounts
the database accepts), and its failure paths: refusal outside staging, staging not up, files judged invalid, server errors. A test (`tests/test_load_test_tool.py`) confirms that the real upload accepts a generated file as valid.

## What the first measurements showed (staging, 7 and 8 October 2026)
Measured on the developer's machine (staging and production share it), with synthetic data. Not a promise about the Bank's server.

| Measure | Result |
|---|---|
| 20 people reading dashboards, 56 requests a second | p95 **391 ms**, no error |
| Sign-in (9 at once) | p95 **0.5 s** |
| Approving a submission | p95 **0.8 s** |
| 8 institutions each uploading 2,000 loans at once | **all took about 16 s** (p95 16.1 s) |
| 8 institutions each uploading 500 loans at once | all took about 5.2 s |
| ONE file of **100,000 loans** (the largest allowed) | accepted, **95.7 s**, no error |

What this says, and what it does not:
* **Uploads are checked one after another, not in parallel**: eight files at once all finished together, after the time of all of them. The backend is one process and checking a file uses
  the processor, so the rate is roughly **1,000 loans a second in total**. Waiting grows with the number of banks uploading at the same time and with file size.
* **The largest file took 96 s, and the web server allowed 120 s**: too close. On a slower machine the person would see a time-out error although the server finished (and uploading again would store a second version).
  Change made: the three endpoints that read a whole file (`/api/submissions/upload`, `/api/climate-data/ingest`, `/api/integration/climate-data`) now have a **300 s** limit in `frontend/nginx.prod.conf`; all other endpoints keep 120 s.
  This gives room; it does not make a 100,000-loan file fast.
* **Not yet measured**: whether one large upload slows the dashboards for other people (`--mixed`), reading at that data size (`read_large`), and the memory a 100,000-loan file needs. Run `--big-rows 100000 --mixed` to see them.
* **Open decision for the Bank**: how large the files really are, and how many institutions upload at the same time (a deadline day). If files of 100,000 loans are expected, checking them in the background
  (the person sees "being checked" and is told when it is done) is the proper design; it is a larger change and has not been made.

### The worst case, measured (`--big-rows 100000 --mixed`, 8 October 2026)
| Measure | Result |
|---|---|
| The largest file (100,000 loans), checked while 20 people kept reading | accepted, `VALID`, **210 s** (96 s when nothing else was happening) |
| People reading **while** that file was checked | p50 466 ms, **p95 1.3 s**, p99 1.8 s, slowest 4.8 s, no error (about 2.4 times slower than normal, not stopped) |
| Approving that file | **11.7 s** |
| Reading the dashboards after it was approved (100,000 more loans) | p95 **0.92 s** (0.50 s before), no error |
| Memory of the backend container | **peak 2.25 GB** (952 MB still held afterwards), no limit set; includes the load-test tool itself |

What this says:
* **The system copes, but a very large upload is slow and heavy**: it more than doubles in time when others are using the system, it slows everyone else by about two and a half times while it runs, and it needs a lot of memory.
  The 300 s limit now given to the file endpoints was necessary: **210 s would have failed under the old 120 s limit.**
* **Where the time goes** (measured on the developer's machine, 100,000 loans): reading the sheet with pandas about 12 s; checking every row about 4 s after the change below (about 14 s before); the rest of the 96 s is **storing the
  100,000 loans in the database**, where each loan was turned into an object held in memory until the commit.

### What was changed because of this (and is waiting to be measured)
1. **The row checks read plain values instead of pandas cells** (`validation_service.py`): the same answers, about twice as fast. Checked by running the old and the new code on the same files: **11,200 records and 117,396 findings from deliberately messy files
   (every kind of wrong value, headers on different rows, blank rows, duplicates), and edge files, were identical**.
2. **The loans and the findings are stored in blocks of 5,000 with bulk INSERTs** (`submissions.py`, `STORE_BLOCK`) instead of one object each. This is the change that should matter most for time and memory; **it could not be run in the environment where it was written**, so the
   full test suite must pass first (`test_upload_storage_blocks.py` checks every block boundary).
3. **Each upload writes one line to the backend log** with its stages: `upload stored: rows=... findings=... validate_s=... store_s=... commit_s=... total_s=... process_peak_mb=...`
   (`docker compose -p cdr-staging ... logs backend | Select-String "upload stored"`). It carries counts and times only, never loan data.
To see the effect run the same worst case again and compare with the table above (96 s alone, 210 s with readers, 2.25 GB).

### After the storage change (8 October 2026): measured, and a second finding
| Measure (the largest file, 100,000 loans) | Before | After |
|---|---|---|
| Alone, as the person experiences it | **95.7 s** | **46 s** |
| Of that, inside the application (from the log line) | not measured | checking **20.5 s**, storing **14.8 s**, commit about 0 s: **35.4 s** |
| While 20 people keep reading | 210 s | 156 s |
| 8 institutions uploading 500 loans each at once | 5.3 s each | 2.8 s each |
| Memory of the backend container (peak, tool included) | 2.25 GB | 1.65 to 1.78 GB |
| Memory of the application process alone (from the log line) | not measured | 526 MB when the file had been stored, **1,487 MB later** |

**The second finding**: the process peaked at 526 MB when the file had just been stored, but at 1,487 MB afterwards, and the person measured 46 s against 35 s inside the application. Something after the storing used about a gigabyte and ten seconds.
It was the **answer**: the answers to an upload and to a review returned the submission object itself, whose `records` and `errors` are all of its rows and findings, so for a file of 100,000 loans the application loaded every loan again and wrote all of them
into the answer (this also explains why approving took 10 s for an action that changes one row, and it would have sent a browser an answer of many megabytes). The detail endpoint had been fixed for this earlier; these two had been missed.
**Changed**: one function (`detail_page`) now builds the answer for the detail endpoint, the upload and the review: one page (the first 100 rows and 100 findings) and the totals. The institution portal uses only `status`, `valid_records` and `total_records` of the answer to an upload, and
nothing of the answer to a review, so nothing on screen changes; a small file's answer is identical to before.
**What is left of the 46 s**: reading the sheet with pandas is now the largest single step (about 15 s of the 20.5 s of checking); storing is 15 s; a further ten seconds was the answer, which this removes. The remaining ideas, in order of size: read the sheet row by row instead of into a table
(a larger change), and checking large files in the background. Both are for later and for the Bank to weigh against how large its files really are.
**To measure again** after this change: the same two runs (`--big-rows 100000`, and with `--mixed`), and read the `upload stored` log lines. Expected: about 35 to 40 s alone and the application process peaking near 600 MB, not 1.5 GB (estimates, not measurements).

### After the answer was paged (8 October 2026): measured
| Measure (the largest file, 100,000 loans, staging) | Start | After bulk storage | **After the paged answer** |
|---|---|---|---|
| Alone, as the person experiences it | 96 s | 46 s | **36 s** |
| Approving that file | about 10 s | about 10 s | **0.23 s** |
| Memory of the backend container (peak, tool included) | 2.25 GB | 1.78 GB | **0.51 to 0.58 GB** (the application alone at most about 0.46 GB) |
| Memory of the load-test tool | 527 MB | 527 MB | 117 MB |
Approving falling from 10 s to 0.2 s confirms the finding: the action itself was cheap, the answer was what loaded every loan.

**Reading the dashboards got slower from run to run** (an earlier version of this paragraph said the number of CURRENT approved loans did not grow: **that was wrong**, see the diagnosis below): `read_large` p95 0.92 s, 1.0 s, 1.9 s, 3.6 s (reading while the large file is checked: 1.3 s, 1.6 s, 2.8 s).
Both the total of stored loans and, as it turned out, the CURRENT approved loans grew (superseded versions are kept on purpose; and every `load_test.py setup` creates new institutions, each set with its own large approved file). The dashboards aggregate in the database (`sum`, `count`, `group by` over current approved submissions), which is the right design;
if the time follows the total rather than the current loans, the database is reading more than it needs (a plan that scans the whole table, or statistics made stale by a bulk load). **Not concluded: to be measured with `scripts/db_diagnose.py`** (read-only):
```
docker compose -p cdr-staging -f docker-compose.prod.yml --env-file .env.staging exec backend python scripts/db_diagnose.py
```
It prints the number of stored loans and of current approved loans, how fresh the planner's statistics are, and, for the two main dashboard queries, whether the plan reads the whole table of loans or goes through an index, with PostgreSQL's own time.
Reading the result: **a whole-table plan whose time follows the total number of loans is a scalability defect** (production will accumulate years of history); the same plan made fast by `ANALYZE` means stale statistics after a bulk load (autovacuum fixes it within about a minute, and the setting can be tuned);
an index plan that is still slow means the cost is the current loans themselves.

### Diagnosis (`db_diagnose.py` on staging, 8 October 2026) and what it led to
**Correction first.** The database held **736,800 loans in all, of which 212,000 were in current approved submissions** (what a dashboard reads): the current data HAD grown, because each `setup` adds a set of institutions with a large approved file. So the dashboards slowed because the data they add up grew,
which is what an aggregate does; it was not the history. The plan that reads the whole table is the right plan here: 29% of the table is wanted, and the statistics were fresh (analysed by the database a minute after the load).
**Where the time goes.** The summary figures (the most requested part of a dashboard) took **1,003 ms** for 212,000 loans, and **about 850 ms of it was sorting the borrowers** to count them once each: `count(distinct customer_id)` sorted 212,000 values **on disk** (`external merge, Disk: 11 MB`) because PostgreSQL's working memory is 4 MB by default.
The by-region query took only **233 ms**. On top of that the application computed the summary with **three separate passes** over the same loans (total loans, total collateral, borrowers), each reading and joining the table again.
**Changed** (`analytics_service.get_kpi_summary`): one pass for the two totals; the borrowers counted as the number of a DISTINCT list (which the database can hash instead of sorting); and 32 MB of working memory for that statement only (`SET LOCAL`, gone when the request's transaction ends; used only as needed, about 13 MB for this many borrowers).
Same figures by definition (NULL and empty customer numbers excluded, as before); a test pins the meaning (one borrower with several loans, one borrower shared by two banks, a submission not yet approved).
`db_diagnose.py` now **times the old and the new way side by side on the real data and checks that the figures are equal**: that, not the load test, is the evidence for this change.
**If that is not enough**, the next step is to remember the summary between requests while the approved data has not changed (the key would be the state of the submissions table, exact because loans are never edited after the upload). It was not done first because a cache that is wrong is worse than a slow page.
The load test reads far faster than people do (a request every 50 to 300 ms per person; a person reading a dashboard waits seconds), so its p95 at 20 readers over-states what 20 real analysts would see. It is still the right test for a deadline day and for growth.
