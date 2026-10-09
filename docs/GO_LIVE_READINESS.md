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
| 9 | Decisions on observations O2 (tokens in browser storage), O9 (one large upload slows others), O10 (read-only file system) | BOT ICT | Each is a documented, accepted-or-not risk. |
| 10 | Phase II: focal persons from each bank, accounts, training, pilot submissions | FSD | Not a software task. |

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
