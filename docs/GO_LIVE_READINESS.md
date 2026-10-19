# Go-live readiness: what the code does, and what only the Bank can supply

Measured against the Concept Note timeline: Phase I (development, security configuration, integration and testing, deployment), then Phase II (focal persons, accounts, training, live submissions). This page separates **what is built** from **what needs a decision, a system or a person at the Bank**.

## Built (verify with the commands at the bottom)

| Area | State |
|---|---|
| External institution portal, sign-in, password recovery, two-step sign-in, roles, tenant isolation | Built and tested |
| Template download, upload, validation, review workflow, audit log | Built and tested |
| Dashboard: summary figures, filters, hazard map, combined climate-financial exposure | Built and tested |
| Dashboard charts as in the mockup: borrower type, currency, loan type, loan by sector / bank / region, collateral by type / sector / region, drill-down region → district → ward | Built (`PortfolioCharts.tsx`, `GET /api/analytics/portfolio-breakdown`) |
| Export: PDF, Excel (now with a Portfolio Breakdown sheet), CSV, PNG | Built |
| QGIS / ArcGIS access (read-only keys, GeoJSON) and live Connected/Not Connected status in the sidebar | Built; not yet run against a live Bank server |
| RTIS / BSIS connection status and health check | Built; data exchange not built |
| Dependency scan (11 Oct 2026): vulnerable packages upgraded and pinned, the scan repeated in CI, two accepted findings explained | Built (`DEPENDENCY_SECURITY.md`) |
| Hazard Summary with the district colour map (no map tiles, so it also works on a closed network) | Built (`DISTRICT_MAP.md`) |
| Sign-in tokens out of browser storage (observation O2): refresh token in an HttpOnly cookie, access token in page memory only | Built and checked on production (`PENTEST_CHECKLIST.md`) |
| Navigation menu reaches every feature of each role; every button that calls the server answers at once and cannot be pressed twice; thin progress bar while waiting | Built (`ICN_REQUIREMENTS_TRACEABILITY_MATRIX.md`, items 100 and 101) |
| Production stack (HTTPS, restricted database role, backups, monitoring, container hardening) and the pre-start configuration checker | Built |

## Needs the Bank (cannot be done in code)

| # | Item | Who | Why it blocks go-live |
|---|---|---|---|
| 1 | Production server, domain name and **TLS certificate** (`./certs`) | BOT ICT | The trial certificate is self-signed (observation O8). |
| 2 | **SMTP** server for temporary passwords (or accept the show-once-to-the-administrator method) | BOT ICT | Otherwise the administrator relays credentials by phone. |
| 3 | **RTIS and BSIS** interface specifications, addresses and credentials | BOT ICT / owners of those systems | The status check works; no data can move until the specification exists. |
| 4 | **Real TMA and PMO data** (and an agreed delivery method: files or the ingest keys) | TMA, PMO via FSD | All climate figures are synthetic until then. |
| 5 | The **official data template** from FSD (the 38-column template in use is described as BOT's own; confirm it is the final version) | FSD | Institutions must all use the same version. |
| 6 | **Decision on map tiles** (observation O11): OpenStreetMap is contacted by the browser | BOT ICT | Closed networks show a blank map. Needs an approved tile source. |
| 7 | **User acceptance testing** with FSD business users, and fixes from it | FSD + development | Phase I, activity 3. |
| 8 | **Independent penetration test** using `docs/PENTEST_CHECKLIST.md`, and fixing its findings | BOT ICT security | The system has not been tested by anyone independent. |
| 9 | Decisions on observations O9 (one large upload slows others), O10 (read-only file system) | BOT ICT | Each is a documented, accepted-or-not risk. (O2, tokens in browser storage, was fixed: HttpOnly cookie.) |
| 10 | Phase II: focal persons from each bank, accounts, training, pilot submissions | FSD | Not a software task. |
| 11 | **Sources for the rest of the Hazard Summary panel** (`HAZARD_SUMMARY.md`; the district colour map is built, see `DISTRICT_MAP.md`): population per district for "affected population" and a rule for what "affected" means, and whether five severity grades are wanted instead of three | BOT ICT + TMA/PMO | Until decided, the panel shows the district map, severity and readings from recorded data only, and shows no population. |
| 12 | **Boundary data for coordinate checks** (`COORDINATE_VALIDATION.md`): confirm with NBS that the ward boundaries may be embedded (the page states no licence); choose the official spelling of 27 ward names (`WARD_NAME_DIFFERENCES.csv` lists each with a suggestion); confirm that 150 districts is right (the former 151st in our list was a duplicate and is removed); decide when a newer boundary file replaces this one | BOT ICT + NBS | Until confirmed, the system uses the NBS public download as published. |

## Run these before declaring Phase I complete

```bash
docker compose exec backend pytest -v                    # all backend tests (includes the new ones)
cd frontend && npm install && npm run build && npx vitest run      # type check and frontend tests
python scripts/prod_setup.py --domain <address>          # once
python scripts/check_production_config.py                # must print READY
./scripts/prod_up.sh                                     # staged start
python scripts/prod_ops.py backup && python scripts/prod_ops.py drill   # a backup and a restore drill
```

Then follow section 3a of `PENTEST_CHECKLIST.md` (Content-Security-Policy check in a browser), and click through every dashboard chart and the drill-down with a BOT analyst account on staging.

## Verified on 11 October 2026 (owner's runs)

Backend **804 passed, 2 skipped** (806 after the place-name fix); frontend **94 passed** (13 files); restore drill **PASSED in 37 s** on near-empty data (`BACKUP_AND_RECOVERY.md`); production updated with `prod_up`, `system_check` OK with an off-machine copy; sign-in cookie checked on production (HttpOnly and Secure, no token in local storage, the session survives a reload).

## Still open on our side (no Bank input needed)

**Scheduled backup (19 October 2026): verified.** The 02:00 task ran by itself with `LastTaskResult 0`, copied the backup off the machine and ran housekeeping. Earlier failures (a battery setting, a locked `backup.log`, Docker Desktop not running at 02:00) are fixed in `prod_ops.py` (Docker wait, retries, own log file, task settings) and covered by `scripts/test_prod_ops.py`; see `BACKUP_AND_RECOVERY.md`.

Load test on staging; repeat the restore drill when there is real data, and agree RPO/RTO with the Bank; a one-page request document for the Bank; a report of the district and ward name differences; the react-router 7 upgrade (done and verified: 94 tests, build, audit; see `DEPENDENCY_SECURITY.md`). The Shapefile ZIP upload and the Concept Note's 50 MB limit are built (`SHAPEFILE_UPLOAD.md`); a 100,000-loan Shapefile ZIP upload was run on staging on 12 October 2026: valid, 76 s, no errors; dashboard reading missed its proposed 1.5 s (p95 1.7 to 1.9 s) on a database full of earlier large test uploads, re-measured on a clean staging: reading 0.9 s (pass); the ZIP of 100,000 loans took 247 s while 20 people were reading (the application is one process, so a mixed load shares it; the upload alone is to be measured without `--mixed`); reading with 100,000 approved loans 1.8 s. The upload alone (no readers) took 17 s, so the ZIP upload is fast; reading figures vary 0.8 to 1.9 s between runs on this machine. Options and the third measurement are in `LOAD_TESTING.md`; to repeat on the Bank's staging server.
