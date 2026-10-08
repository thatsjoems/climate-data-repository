# ICN Requirements Traceability Matrix

Source: "Concept Note on the Proposed Enhancement of the Climate Data Repository" (Bank of Tanzania, Financial Stability Department).

| # | ICN Requirement (as stated in the Concept Note) | Status | Where it was built (System Component) |
|---|---|---|---|
| 1 | Secure external access for reporting institutions | **IMPLEMENTED** | Separate login + `INSTITUTION_USER` role, data isolation by `institution_id` |
| 2 | Login and Role-Based Access Control | **IMPLEMENTED** | `backend/app/core/security.py`, `deps.py` (JWT + RBAC guards) |
| 3 | Separate interfaces for external institutions vs. BOT users | **IMPLEMENTED** | `InstitutionPortal.tsx` vs `InternalPortal.tsx` (frontend) |
| 4 | Download Template (standardized Excel) | **IMPLEMENTED** | `GET /api/templates/loan-collateral/download` |
| 5 | Upload of completed data | **IMPLEMENTED** | `POST /api/submissions/upload` |
| 6 | Automated data validation and error feedback | **IMPLEMENTED** | `validation_service.py` + `ValidationError` model |
| 7 | Submission history / tracking | **IMPLEMENTED** | `GET /api/submissions` (institution-level data isolation) |
| 8 | BOT dashboard with overview of submissions, loans, collateral, climate data | **IMPLEMENTED** | `InternalPortal.tsx` + `/api/analytics/kpi-summary` |
| 9 | Advanced filtering (institution, period, geography, hazard) | **IMPLEMENTED** | Dashboard Filters panel (`InternalPortal.tsx`) lets a BOT Analyst narrow KPI Summary, Hazard Exposure, and Combined Climate-Financial Exposure by institution, region, and reporting period simultaneously (`filter_institution_id`/`filter_region`/`filter_reporting_period` query params, added to `analytics_service.py`'s `_active_records_query()` and threaded through all three endpoints). Filters only ever narrow an already tenant-scoped view - they cannot widen access |
| 10 | Dashboard Export (PDF, Excel, CSV, image) | **FULLY IMPLEMENTED** | BOT_USER: `GET /api/reports/summary.pdf`, `/summary.xlsx` (multi-sheet), `/summary.png` (single-image dashboard snapshot - KPI summary + hazard exposure bar chart, rendered with Pillow), `/combined-exposure.csv`. INSTITUTION_USER: `GET /api/submissions/export.csv` (own submission history, isolated). SYSTEM_ADMIN: `GET /api/audit-logs/export.csv` (honors the same filters as the on-screen list). All four formats the ICN names explicitly are now covered |
| 11 | Password recovery workflow | **IMPLEMENTED** | Public "Forgot Password" page (`ForgotPassword.tsx` → `POST /api/password-reset-requests`) creates a reset request without revealing whether the account exists; a SYSTEM_ADMIN reviews and approves/rejects it, generating a new temporary password shared out-of-band |
| 12 | Integration with RTIS, BSIS, QGIS, ArcGIS | **NOT YET IMPLEMENTED - Out of scope (Future/Mock)** | No real credentials/API access were provided. Backend design (modular API routers) is "integration-ready" but no real adapter has been built. **Note:** the Geospatial Overview map itself was built independently of these systems — see item 12b and `docs/GEOSPATIAL_MAP.md` |
| 12b | Geospatial visualization of climate/financial exposure | **IMPLEMENTED (region-level)** | `GET /api/analytics/map-points` + `HazardMap.tsx` render an interactive map (Leaflet + OpenStreetMap - free, self-hosted, no external GIS dependency) plotting real hazard-exposure figures at real region-centroid coordinates. Deliberately self-sufficient per explicit direction: the system should operate on institution-submitted + own climate data alone, not depend on an external map service. Precise per-loan coordinates await BOT's forthcoming data template (see `docs/GEOSPATIAL_MAP.md`) |
| 13 | Institutional onboarding (focal person nomination) | **REMOVED per BOT operational preference** | A public self-service "Request Access" form was originally built (a prospective institution submits details, SYSTEM_ADMIN approves), but was subsequently removed entirely at BOT's explicit instruction. Onboarding is now purely Admin-driven: a SYSTEM_ADMIN creates the Institution and User directly via the Administration page - no public request/approval step exists anymore |
| 14 | Audit logging | **IMPLEMENTED** | `AuditLog` model + `audit_service.py`, records LOGIN, SUBMISSION_CREATED, USER_CREATED, etc. |
| 15 | Climate risk assessment for the banking sector (exposure analysis and supervisory reporting) | **IMPLEMENTED** | Descriptive exposure-by-region/hazard data (`analytics_service.get_hazard_exposure()`) feeds a dedicated **Risk Advisory Reports** module (`risk_advisories.py`, `RiskAdvisoryNote` model), where the BOT Analyst authors climate-risk assessments and recommendations for internal decision-making, grounded in a real, queried data snapshot captured at the time of writing. Consistent with the "no fabricated risk score" rule: the system never computes or infers the risk level itself — that judgement is always the analyst's own, attributed and timestamped |
| 16 | **Core project AIM**: combine financial sector data with climate/meteorological data | **IMPLEMENTED** | `analytics_service.get_combined_climate_financial_exposure()` (`GET /api/analytics/combined-climate-financial-exposure`) joins real `ClimateRecord` readings (rainfall, temperature, hazard) with real `SubmissionRecord` loan/collateral exposure for the same region and reporting period. Previously these two datasets existed in isolation (climate_hazard_exposure was only self-reported by institutions); this view is the first place the two are actually queried together |
| 16 | Meteorological data integration (TMA) | **SAMPLE/SYNTHETIC** | `ClimateRecord` table is populated with SAMPLE (synthetic) data tagged `source="SYNTHETIC_SAMPLE"` - NOT real TMA data |
| 17 | Climate Vulnerability Maps (PMO) | **IMPLEMENTED (visual overlay)** | An optional PMO/GCA hazard tile layer (Flood/Drought, discovered public endpoint at `tcvmp.pmo.go.tz`) renders underneath our own institution-exposure markers on the Geospatial Map — see `docs/GEOSPATIAL_MAP.md` for exactly how this was found and its "unofficial endpoint" caveat. This is a visual overlay only, not a data-sharing pipeline; QGIS/ArcGIS themselves remain unconnected (item 12) |

## Summary

**See `docs/SECURITY_HARDENING.md`** for a detailed record of a subsequent
security/data-integrity hardening pass: multi-tenant analytics isolation,
duplicate/superseded-submission handling, invalid-can't-be-approved and
maker-checker workflow rules, upload limits, district-region validation,
brute-force login protection, forced password change on temporary
credentials, reduced institution info disclosure, and a paginated audit log
viewer. That document also lists what was deliberately left out as outside
the ICN's scope (e.g. database migrations, JWT/cookie rearchitecture).

**Later still, a full audit-and-harden pass** extended the climate data
architecture: `ClimateRecord` gained provenance/quality-control fields
(station, dataset, quality_flag, ingestion_timestamp, etc.), a real TMA
file-ingestion adapter was built (`POST /api/climate-data/ingest`) with
validation, duplicate detection, and per-batch provenance tracking, and a
Data Quality dashboard was added for the Analyst. See
`docs/TMA_INGESTION.md` for the full architecture and exactly what remains
to connect real TMA data. CSV export was also added for Combined
Climate-Financial Exposure, and misleading "Real meteorological readings"
wording was corrected to dynamically warn when the underlying data is
synthetic.

**A further role-separation refinement** was applied on top of the security
hardening pass: SYSTEM_ADMIN's dashboard is now strictly administration-only (users,
institutions, access requests, password resets, audit log) with zero
visibility into climate data, submissions, or analytics; BOT_USER (the
Analyst) is conversely the only internal role with access to any data/climate
content, and has no visibility into administration matters (audit log, user
list, access/password-reset requests). Institution users additionally gained
the ability to review the actual rows they submitted (not just validation
errors) and re-download their original uploaded file. See
`docs/ROLE_SEPARATION.md` for the full before/after permission matrix.

**Session security upgrade**: access tokens were reduced from 8 hours to 15
minutes, backed by a separate, revocable, rotated refresh token (see the
"Session security upgrade" section of `docs/SECURITY_HARDENING.md`) — a
stolen token is now only useful for a small window, and "Log Out" actually
revokes the session server-side instead of only clearing local storage.

**Visual identity**: the interface now uses Bank of Tanzania's actual
branding — extracted directly from the ICN document's own mockup images
(logo, dark/gold color scheme) — rather than a generic placeholder theme.


- The entire **MUST HAVE** workflow (login → template → upload → validation → storage → internal review → dashboard) has been **built and fully functional**.
- **SHOULD HAVE** items (export, advanced filters, password recovery) are now **all implemented**, including image export - see items 9, 10, and 11 above.
- **FUTURE WORK** (live RTIS/BSIS/QGIS/ArcGIS integration, real TMA/PMO data) - not possible without real access/credentials from BOT - these are clearly documented as gaps, not hidden.

## Data-integrity fix (after external review): Combined Climate-Financial Exposure honesty

An external review correctly identified two real weaknesses in
`get_combined_climate_financial_exposure()` — verified against the actual
code, not just accepted on claim:

1. **No `quality_flag` filtering**: SYNTHETIC, UNVALIDATED, VALIDATED, and
   FLAGGED climate readings were all silently blended into one average with
   no indication of composition.
2. **Weak period matching**: climate records were matched only by
   reconstructing year/months from the quarter, never by the record's own
   `reporting_period` field (even though that field exists and is populated
   by the ingestion pipeline).

**Fixed**: FLAGGED readings (explicitly analyst-rejected) are now excluded
outright from any average. Matching now prefers an exact
`reporting_period` match, falling back to year/month reconstruction only
for legacy records with no `reporting_period` set. Every combined-exposure
row now carries a `climate_data_quality` field — `"VALIDATED"` only when
every contributing reading is validated, otherwise `"MIXED (...)"` naming
exactly which quality flags contributed — surfaced in the dashboard table,
the PDF/Excel reports, and the CSV export. See
`tests/test_combined_exposure_quality.py` for the regression tests locking
this in.

## MAJOR UPGRADE: Official BOT Template Adopted (38 columns)

The submission template, database model, and validation engine were
completely rebuilt around **Bank of Tanzania's own official Climate Data
Template** (provided directly by the user, along with the 2022 Census
village/mtaa list and the Zanzibar Frame) - replacing the earlier
9-column prototype template entirely.

**What changed:**
- `SubmissionRecord` now has BOT's exact 38 fields (Customer ID, Client
  Type, Business Size, full loan terms, separate location + GPS for BOTH
  the loan and its collateral, and climate-risk insurance details) instead
  of a simplified 9-field subset.
- All dropdown option lists (Client Type, Collateral Pledged - 21 real
  categories, Loan Economic Activity, Asset Classification, etc.) now match
  BOT's own official "DROP DOWN" reference sheet exactly, not an
  approximation sourced from a BOT report.
- **Region -> District -> Ward -> Village/Street cascading dropdowns**, four
  levels deep, built from the real 2022 Census hierarchy (31 regions, 151
  districts, 4,342 wards/shehia, 19,946 villages/mitaa) - applied
  independently to both the loan's own location and the collateral's
  location. Verified working at full scale via LibreOffice (see
  `app/services/geo_lookup.py` for the data, `template_generator.py` for
  the Excel-side INDIRECT()-based implementation, including correct
  handling of apostrophes and other special characters in real place names).
- **GPS-region consistency check**: a row's stated latitude/longitude is
  flagged (WARNING, not a hard rejection - see `validation_service.py` for
  why) when more than 300km from the selected region's own centroid. This
  is an honest approximation - we have region centroids, not district/ward
  boundary polygons, so it catches gross mismatches without false-flagging
  correct points in Tanzania's largest regions.
- The per-row `reporting_period` column was removed - BOT's own template
  states the reporting date ONCE per file ("LOAN AND COLLATERAL DATA AS AT
  ___"), not per row, so the reporting period is now form-only, attached to
  the Submission as a whole.
- `customer_id` (BOT's real identifier) replaces the invented `borrower_name`
  field as the "who is this loan for" identifier throughout Total Borrowers
  and related KPIs. `borrower_name` remains on the model as an unused,
  nullable legacy column so nothing referencing old data breaks.

**Known consequence, stated plainly**: BOT's official template has no
self-reported hazard-exposure column (hazard is meant to come from joining
with TMA/PMO climate data by region - exactly what Combined
Climate-Financial Exposure already does), so the institution-self-reported
"Hazard Exposure" pie chart will show every new submission as hazard
"None" going forward. Fixing this properly means recomputing hazard
exposure from the region-based climate join instead of a self-reported
column - not done in this pass, flagged here rather than left silently
broken.

## Second external review — fixes applied

A second external review correctly identified three further issues, verified against actual code before fixing:

1. **Risk Advisory snapshot bug**: `get_exposure_snapshot()` could surface a
   FLAGGED (analyst-rejected) reading as the "latest climate reading" in an
   advisory note, and its `hazard_type` filter used the dead self-reported
   `climate_hazard_exposure` field (never populated since the official
   template has no such column). Both fixed: FLAGGED is now excluded
   everywhere a climate figure is presented, and hazard filtering resolves
   via real `ClimateRecord.hazard_type` matches, consistent with Hazard
   Exposure and Combined Exposure.
2. **VALIDATED-only toggle**: Hazard Exposure and Combined Exposure now
   accept a `validated_only` flag (UI checkbox in `InternalPortal.tsx`) so
   an analyst can switch between an exploratory view (everything except
   FLAGGED - useful while most data is still SYNTHETIC/UNVALIDATED) and a
   strict official view (VALIDATED readings only). This was a deliberate
   design choice over hard-coding VALIDATED-only everywhere: doing so today
   would leave these views empty, since almost nothing has been through a
   real human QC step yet.
3. **Advanced filtering** (item 9 above) was completed in direct response
   to this review.

**Earlier decision (superseded):** a manual "Validate/Flag" QC UI was initially
deferred. That decision was later reversed because `quality_flag=VALIDATED`
would otherwise be unreachable through an operational workflow. The current
QC implementation is documented in the next section.

The earlier QC deferral was reconsidered after a third review made a more compelling architectural
argument than the one that led to deferring it: without ANY promotion
action, `quality_flag=VALIDATED` would be permanently unreachable in the
ENTIRE system - not just during the interim manual-bridge period, but even
after real, live TMA integration exists, since an automated feed alone was
never going to self-assign VALIDATED either. That is a structural gap in
the quality_flag system itself, not merely a missing "nice to have" UI.
Three items were implemented in response:

1. **Climate QC promotion**: `POST /api/climate-data/promote` lets a BOT
   Analyst mark all UNVALIDATED readings for a (region, reporting_period) as
   VALIDATED or FLAGGED - the one action that makes VALIDATED reachable.
   Scoped to region+period rather than a single row or an ingestion batch,
   because `ClimateRecord` has no batch foreign key (see
   `ClimateIngestionBatch`'s own docstring) and per-row promotion would not
   scale to real TMA data volumes; region+period is also exactly how climate
   data is already looked up everywhere else (Combined Exposure, Hazard
   Exposure, Risk Advisory). SYNTHETIC and already-FLAGGED/VALIDATED readings
   are never touched by this action. `GET /api/climate-data/unvalidated-groups`
   lists what is currently awaiting review. UI: a new table in the "Climate
   Data Quality" section of the Analyst dashboard.
2. **Risk Advisory tightened to VALIDATED-only**: unlike the exploratory
   dashboard views (which default to "everything except FLAGGED", with an
   optional VALIDATED-only toggle), `get_exposure_snapshot()` now ALWAYS
   requires quality_flag == VALIDATED for both the hazard-type filter and the
   attached "latest climate reading" - no toggle, no exception. A Risk
   Advisory Note is a formal, archived document; if no VALIDATED reading
   exists, the response includes a plain `climate_data_note` saying so
   instead of silently attaching SYNTHETIC/UNVALIDATED data.
3. **Reports now honor Dashboard Filters**: the PDF, Excel, and CSV exports
   accept the same `filter_institution_id`/`filter_region`/
   `filter_reporting_period`/`validated_only` parameters as the dashboard,
   and every report states plainly which filters (if any) were active -
   never ambiguous about whether a figure is sector-wide or narrowed.

## Fourth external review — fixes applied

Six issues from a fourth review were verified against actual code and fixed:

1. **Map filter desynchronization (HIGH)**: `/analytics/map-points` did not
   accept `validated_only`/`filter_institution_id`/`filter_region`/
   `filter_reporting_period`, so the Geospatial map could silently keep
   showing sector-wide/unfiltered data while the dashboard's KPI cards and
   charts were correctly filtered - a serious consistency risk on a
   supervisory screen. Fixed: `get_region_map_points()` now accepts and
   applies the exact same filters, and every frontend function that refreshes
   filtered data (`loadAll`, `reloadClimateExposureViews`,
   `applyDashboardFilters`, `resetDashboardFilters`) now refreshes the map too.
2. **Risk Advisory temporal mismatch (HIGH)**: the attached "latest climate
   reading" was matched by region only, so an advisory about Q2 could show a
   Q4 reading just because it was more recent. Fixed: `RiskAdvisoryNote`
   gained an optional `reporting_period` field (UI: a dropdown on the
   advisory form); when set, `get_exposure_snapshot()` restricts BOTH the
   financial exposure total and the attached climate reading to that exact
   period, with the same region+period matching logic (direct match,
   year/month fallback for legacy records) used by Combined Exposure.
3. **Climate physical plausibility**: rainfall (0-5000mm), temperature
   (-20 to 55°C), latitude (-90 to 90), longitude (-180 to 180) are now
   range-checked on ingestion, and temperature_min/avg/max are checked for
   internal consistency (min ≤ avg ≤ max) when more than one is present.
4. **Hazard normalization**: "Flood", "flood", "FLOOD", "Flooding" (and
   similar variants for Drought/Cyclone/Landslide) now all normalize to the
   same canonical value used everywhere else in the system
   (`template_generator.HAZARD_OPTIONS`) on ingestion. An unrecognized value
   is rejected rather than silently kept as a fragmenting free-text category.
5. **Source provenance control**: the climate ingestion "source" field was
   free text, so an analyst could label any manually-uploaded file
   an official-looking `TMA_FILE` label, indistinguishable from a genuinely verified feed once stored.
   Now restricted to `MANUAL_TMA_FILE` / `MANUAL_PMO_FILE` /
   `MANUAL_OTHER_FILE` - every option is honest that this is a human's
   self-declared belief about origin, not a verified integration. No
   "official"/"verified" option exists, since none would be true yet.
6. **"Dominant hazard" terminology**: dashboard wording changed from "Flood
   Loan Exposure" (implies each loan was individually affected) to "Loan
   Exposure in Regions/Periods with Recorded Flood Hazard" (accurately
   describes what the figure actually is - a regional climate pattern
   association, not a per-loan claim).

All six are covered by new/updated tests (`test_climate_ingestion.py`).

## Fifth external review — fixes applied

Five issues fixed after this review confirmed all prior major fixes held:

1. **Stale "institution-reported climate hazard" wording** in the PDF/Excel
   reports (`report_service.py`) - now correctly says hazard exposure comes
   from real `ClimateRecord` observations, not institution self-reporting.
   Column headers changed from "Hazard"/"Loan Exposure" to "Recorded Hazard"/
   "Loan Exposure in Region/Period" for the same reason, matching the
   dashboard wording fixed in the previous review round.
2. **VALIDATED-only is now the default**, not an opt-in: the dashboard's
   checkbox defaults to checked, and the `validated_only` API/report
   parameters default to `true`. An analyst can still switch to the
   exploratory view (include SYNTHETIC/UNVALIDATED) with one click, but the
   default a supervisory dashboard opens to is now the conservative one -
   only the underlying service-layer Python defaults were left at `False`
   (they're always explicitly overridden by the API layer, and several
   existing tests call them directly expecting the permissive default).
3. **Climate duplicate-detection precision**: `station_id` was added to the
   dedup key (alongside region/district/year/month/source_record_id) -
   without it, two genuinely different stations reporting for the same
   district/month with no `source_record_id` would collide on the same key,
   and the second station's real observation would be wrongly rejected as a
   duplicate.
4. **Self-declared source disclaimer**: the Climate Data Ingestion form now
   states plainly, next to the source dropdown, that the TMA/PMO option is
   the analyst's own belief about origin and is not independently verified.
5. **QC reason field**: `POST /api/climate-data/promote` now accepts an
   optional `reason` (UI: a text box next to each Validate/Flag row),
   recorded in the audit log entry - closing the "no justification for a QC
   decision" governance gap raised in two separate reviews.

## Sixth external review — fixes applied

Two further issues verified against actual code and fixed:

1. **KPI filter self-availability bug**: when an INSTITUTION_USER's security
   scope (`institution_id`) and an analytical `filter_institution_id` were
   both passed into `_active_records_query()`, they were ANDed together as
   two separate conditions on the same column - if they ever differed (e.g.
   a stale/leftover filter value), the query became a contradiction
   (`institution_id = 'A' AND institution_id = 'B'`), silently returning
   ZERO records instead of the institution's own real data. Fixed: the
   security scope now always wins, and the analytical filter is force-
   cleared to `None` whenever a security scope is already present -
   confirmed via `test_institution_user_cannot_widen_kpi_with_filter_institution_id`.
   Also fixed in the same pass: the KPI's "Total Submissions" count did not
   previously respect `filter_region`, while "Total Loan Exposure" did -
   an inconsistency within one dashboard view. Both now join through
   `SubmissionRecord` and apply the same region filter.
2. **PENDING/INVALID submissions could enter exposure analytics**:
   `EXCLUDED_STATUSES` only excluded REJECTED and SUPERSEDED, so a row from
   a submission still awaiting validation (PENDING) or one whose file
   overall failed validation (INVALID - "awaiting correction", and which
   can never be directly approved without a corrected resubmission) could
   still count toward official exposure figures purely because that
   individual row happened to pass row-level checks. Fixed: only VALID and
   APPROVED submissions now contribute - confirmed via
   `test_pending_and_invalid_submissions_do_not_enter_exposure_analytics`.
   Pre-existing tests were unaffected, since the shared `_seed_submission_for`
   test helper already used VALID status.

Also corrected: `docs/TMA_INGESTION.md` still described the climate
duplicate-detection key without `station_id`, contradicting the actual key
used since an earlier fix - now consistent.

## Seventh external review — database-integrity fixes applied

A review focused specifically on database design (not just application logic)
found the schema's biggest gap: several integrity guarantees existed only in
Python, not in the database itself. Verified and fixed:

1. **`climate_records` had no link to the batch that created it.**
   `source`/`dataset_name`/`station_id` described an observation's origin in
   free text, but "which upload produced this row?" was not directly
   answerable from the database. Fixed: `climate_records.batch_id` is now a
   real foreign key to `climate_ingestion_batches.id`, set at ingestion time
   (nullable, for any legacy rows) - confirmed via
   `test_ingested_records_are_linked_to_their_batch`.
2. **Ingestion audit event was a separate transaction from the data it
   described.** The batch, its accepted records, and its rejected-row errors
   committed first; the audit log entry committed afterward, in its own call.
   A failure between the two could leave climate data saved with no audit
   trail of it. Fixed: `record_audit()` gained an optional `commit=False`
   mode (defaults to `True` everywhere else, so no other call site changed
   behavior); the ingestion endpoint now flushes the audit event and commits
   everything - batch, records, errors, audit log - together, once.
3. **Missing indexes on several real query/filter paths** - composite
   indexes added for `submissions(institution_id, reporting_period, status)`,
   `submission_records(submission_id, loan_id)`, `climate_records(region,
   reporting_period, quality_flag)`, and similar, matching how these tables
   are actually filtered elsewhere in this codebase (not indexed "just in
   case").
4. **Controlled schema evolution with Alembic.** Database changes are now
   represented by reproducible migration revisions. Existing pre-Alembic CDR
   databases are baselined without deleting their data, then upgraded through
   the integrity migration. Duplicate data is never silently deleted or merged.
   Fresh databases are created exclusively through the migration chain.
5. **Seed data no longer fakes a human QC decision.** Two hardcoded demo
   rows previously seeded `quality_flag = VALIDATED` / `FLAGGED` directly -
   states meant to represent a real BOT Analyst's judgement on real ingested
   data. Removed: seed/demo climate observations now stay `SYNTHETIC`
   throughout, matching the QC promotion endpoint's own existing rule that
   SYNTHETIC rows are never reclassified as if a human had reviewed them.
   **Operational consequence:** a freshly-seeded environment has no
   VALIDATED climate data until someone actually ingests a file (e.g.
   `climate_31regions_synthetic.csv`) and promotes it via Climate Data
   Quality - Risk Advisory/Combined Exposure will show "no VALIDATED
   observation available" until that step is done. This is intentional, not
   a defect: it demonstrates the full pipeline rather than a shortcut.

Left deliberately unimplemented, per the review's own caution against
premature constraints: a database-level UNIQUE constraint for climate
observation identity or `(institution, reporting_period, loan_id)` (nullable
source/station identifiers and SUPERSEDED-submission versioning both need a
clearly-defined canonical rule first, or a blind constraint would reject
legitimate data); `reporting_period` as a real date-dimension type;
`data_snapshot`/`audit_logs.details` moving from Text to JSONB. All three
are noted here as known, intentionally-deferred future work, not gaps
anyone should be surprised by later.

## Eighth external review — Alembic migrations, database-level integrity

This review added Alembic-based migrations (replacing the additive
`ensure_postgres_compatibility()` bridge), database-level CHECK constraints
across financial and climate fields, and two partial unique indexes enforcing
climate-observation duplicate prevention at the database layer itself (not
just in application code). Verified and merged, with two critical defects
found and corrected before merging - not accepted on the strength of the
reviewer's own "ALEMBIC_UPGRADE_OK" claim alone:

1. **The `reporting_period` format CHECK constraint would have rejected every
   valid value.** `substr(reporting_period, 6, 1) IN ('1','2','3','4')`
   checks position 6 of e.g. `"2026-Q3"` - which is always the literal
   character `'Q'`, never a digit. Confirmed by executing the exact
   constraint against a real SQLite database: a plainly valid value like
   `"2026-Q3"` was rejected. This would have made every submission upload
   fail once the migration ran. Fixed to check position 7 (the actual
   quarter digit) in both `models.py` and the migration file, then
   re-verified against 7 real/invalid values including edge cases
   (`"2026-Q5"`, `"2026Q1"`, `"26-Q1"`) - all now resolve correctly.
2. **`init_db.py` tried to Alembic-stamp a revision ID that does not
   exist.** It called `alembic stamp e9e9d40a61d2` to baseline a
   pre-Alembic database, but neither migration file uses that revision
   ID (the real initial-schema revision is `d2616a6f36ac`). Alembic
   validates that a stamped revision exists, so this would have crashed
   `init_db.py` for exactly the case it was meant to handle: upgrading
   an existing CDR database (such as this project's own, from every prior
   session) rather than a brand-new one. Fixed to reference the correct
   revision ID.

Both defects were the kind that only surface when data is actually
inserted, or when upgrading a pre-existing database - neither is exercised
by "does the migration file run on an empty database" testing, which
matches the reviewer's own disclosure that the full pytest suite could not
be run in their environment (missing `passlib`, no network access to
install it). The duplicate-prevention indexes themselves were verified
correct against 5 real-database scenarios (true duplicate by
`source_record_id`, true duplicate by `station_id` alone, two observations
with no identifiers at all - correctly both allowed, since neither can be
proven duplicate - and a distinct station correctly allowed).

Also added: an `IntegrityError` catch around the climate-ingestion commit,
returning a clear HTTP 409 instead of a raw 500 if a genuine concurrent
upload ever collides with the new database-level uniqueness guarantee -
the database-level protection this review added is a real backstop now,
but a caught, explained conflict is better than an unhandled crash.


## Ninth review — independent re-verification of the eighth review's fixes

A separate reviewer, given only the original (pre-fix) uploaded ZIP from the
eighth review, independently re-derived both critical defects above and
confirmed them against the same file paths - a useful cross-check, since it
reached the same conclusions through its own reading of the code rather than
trusting this project's account of them. It also correctly noted that the
fixes were absent from *that particular ZIP* (accurate for the file it was
given) and raised one additional, genuinely useful point that this project's
own fix had not yet covered:

**The legacy-database preflight was checking table names only, not actual
columns.** `expected.issubset(tables)` confirms every CDR table exists, but
says nothing about whether a given table's *columns* match what revision
`d2616a6f36ac` assumes - a table-name match cannot tell a fully-caught-up
legacy database (every real deployment of this project, since the prior
`ensure_postgres_compatibility()` bridge already added `climate_records.batch_id`
before Alembic existed) apart from an older, partially-migrated one for which
stamping at this baseline would be silently wrong. `init_db.py`'s
`ensure_schema()` now also checks that `climate_records.batch_id` actually
exists before stamping a legacy database at `d2616a6f36ac`; if the tables
exist but that column doesn't, it raises a clear error and refuses to guess,
rather than risk a mismatched stamp that later migrations would silently
build on.


## Production-hardening pass — pagination, rate limiting, observability, storage, frontend tests

Following a self-review that named seven concrete production-readiness gaps
(none of them blocking the ICN's core functionality, all of them real), five
were addressed directly and two were confirmed to require resources this
project cannot provide on BOT's behalf:

1. **Pagination.** `GET /submissions` returned every matching row
   unconditionally. Now backward-compatible: called with no `page` parameter
   (as both current frontend screens do), it behaves exactly as before;
   passing `page`/`page_size` returns a bounded slice with the true count in
   an `X-Total-Count` header. `risk_advisories` was similarly capped at 200
   rather than left unbounded.
2. **Rate limiting.** The existing per-account lockout (Module A) stops
   repeated guesses against ONE username, but nothing previously stopped one
   IP from trying many different usernames. `slowapi` now enforces a
   200/minute default across the API and a tighter 10/minute on
   `/auth/login` specifically, in-memory (no Redis needed at this
   deployment's scale).
3. **Structured logging.** `app/core/logging_config.py` gives every log
   line a consistent shape - JSON in production (for a real log
   aggregator), readable text in development - and a new request-logging
   middleware records method/path/status/duration for every request. This
   is deliberately NOT a Sentry/error-tracker integration, which needs a
   real account/DSN this project cannot provision; it follows the same
   optional-activation shape as `email_service.py` elsewhere in this
   codebase, ready for one to subscribe to later.
4. **Storage abstraction.** File uploads were saved via direct `os.*` calls
   inside the submissions endpoint. `app/services/storage_service.py` now
   sits between them: a `StorageBackend` interface with a `LocalFileStorage`
   implementation matching today's exact behaviour byte-for-byte (same
   directory, same UUID naming, same `file_path` semantics the download
   endpoint already depends on) - so that a future S3-backed implementation
   is a new class and one config value, not a search-and-replace through
   every endpoint that touches a file.
5. **Frontend tests.** Zero existed. Vitest + React Testing Library were
   added, with tests for `ProtectedRoute` (every branch of the frontend's
   own role/access-control logic: no user, forced password change, wrong
   role, correct role, no role restriction) and the API client's token
   interceptor (Bearer header attached when a token exists, absent when it
   doesn't) - chosen because both are genuine access-control logic, not
   incidental UI. The CI workflow now runs `npm test` before the build.
   **Honesty note:** this sandbox has no network access to install the new
   npm dependencies, so these tests were verified by careful manual
   cross-checking against `AuthContext.tsx`'s actual exported shape (every
   field the tests assume was confirmed present, by name, in the real
   source) rather than by an actual `npm test` run. Treat them as
   logically-verified-but-not-yet-executed until run for real.

Confirmed NOT completable by this project on its own:
- **Real SMTP email delivery** - `email_service.py` already degrades
  gracefully with no `SMTP_HOST` set (shows credentials to the approving
  admin instead of silently failing); sending real email needs a real SMTP
  account BOT would provide, not a code change.
- **Solution 4 (RTIS/BSIS/QGIS/ArcGIS integration)** - unchanged from every
  earlier note on this: architected and integration-ready, but requires
  credentials only BOT can issue.


## Tenth review — three independent additions, merged alongside the hardening pass

This review was built from an earlier snapshot of the project (before the
production-hardening pass immediately above), working in parallel rather
than reviewing it - most of its file differences were simply that earlier
snapshot's versions of files this project had since already improved
independently (pagination, rate limiting - `auth.py`, `submissions.py`,
`risk_advisories.py`, `ci.yml`, `requirements.txt`, `package.json` all
matched an older state and were kept as-is, not reverted). Three files
contained genuinely new, non-overlapping contributions and were merged in:

1. **Streaming audit-log CSV export.** `GET /audit/export.csv` previously
   loaded every matching row into memory before writing any of the response
   (`query.all()`, then one `csv.writer` pass) - the same unbounded-query
   pattern named elsewhere in this project, just in a file this project's
   own pagination pass hadn't reached yet. Now streams in batches of 1,000
   rows via a generator, so a large export's memory footprint stays flat
   regardless of how many audit log rows actually match the filter.
2. **Non-root container user.** The backend Dockerfile now creates and
   switches to an unprivileged `cdr` user (uid 10001) before `CMD` runs,
   with `/app` explicitly `chown`'d to it beforehand. Running the API
   process as root inside its container was unnecessary exposure - a
   compromised process gains less if it was never root to begin with. Port
   8000 needs no special privilege to bind (only ports below 1024 do), so
   this has no effect on how the container is reached.
3. **Production seed guard.** `init_db.py` now exits immediately, before
   touching the database, if `ENVIRONMENT=production` - skipping the demo
   institutions/users entirely rather than relying on "skip if data already
   exists." Every demo credential this project uses (`admin`/`Admin@123`
   and the rest) is published in this project's own README and
   presentations for training purposes; auto-creating them in a real
   deployment would be a real credential-exposure risk, not a training
   convenience. `docker-compose.yml`'s own default
   (`ENVIRONMENT:-development`) means this is a no-op for this project's
   actual demo/training use - it only activates when someone explicitly
   deploys with `ENVIRONMENT=production` set.

All three compile cleanly alongside the hardening pass's own additions
(rate limiting, logging, storage abstraction, pagination) with no overlap
or conflict - confirmed by re-running `py_compile` across the full `app/`
tree after merging.


## Critical finding — CHECK constraints never actually reached the real database

Caught directly from a live database, not a code review: running `\d
climate_records` in psql against this project's own real, running
PostgreSQL instance showed every expected column, index, and foreign key -
but **no "Check constraints:" section at all**. Every financial/climate
CHECK constraint documented in the eighth review above (amounts ≥ 0, GPS
bounds, `reporting_period` format, temperature plausibility, valid
quality_flag/period_type/hazard_severity) existed only as a Python
`CheckConstraint(...)` declaration in `models.py` - never actually enforced
by PostgreSQL on the database anyone would actually be running.

**Root cause:** `d2616a6f36ac`'s CHECK constraints are declared as part of
its own `op.create_table()` calls, which only execute their DDL against a
genuinely fresh, empty database. `init_db.py`'s legacy-database path calls
`alembic stamp d2616a6f36ac` for a database whose tables already existed
from before Alembic did - and `stamp` only records "this revision is
considered applied" in the `alembic_version` table; it never executes that
revision's `create_table()` calls, since the tables already exist and
there is nothing to create. Every constraint that migration was supposed
to add via `CREATE TABLE` was therefore silently skipped on every database
that reached this schema via that legacy path - which, since this
project's own database has existed since before Alembic was introduced, is
every real deployment of this project to date, including this one.

**Why this was not caught in the eighth review's own verification:** that
round tested the migration's SQL logic directly against SQLite (proving
the *constraint conditions themselves* were correct once applied) and
confirmed `alembic upgrade head` completed without error - both true, and
neither one exercises the specific stamp-then-upgrade code path a real
legacy database actually takes. The gap was only visible by inspecting an
already-migrated, real database's actual constraints - exactly what
surfaced it here.

**Fix:** a new migration, `9c1852419557` (chained after `8b2f5c1e9a44`, not
edited into it or into `d2616a6f36ac` - both have already run against real
deployments, and Alembic tracks "already applied" by revision ID, not by
re-diffing a file's contents, so editing an applied migration changes
nothing for a database that already recorded it as done). It re-asserts
all 25 CHECK constraints, each guarded by an existence check via
`inspector.get_check_constraints()`, so it is correct whether run against
a legacy database missing them entirely (the real case) or a hypothetical
fresh one where `create_table()` already added them (the check finds them
present and does nothing).

**This requires one more step on any already-running deployment of this
project, including this one:** `docker compose up` alone re-runs
`init_db.py`, which calls `alembic upgrade head` - and upgrading from
`8b2f5c1e9a44` to the new head (`9c1852419557`) is exactly what applies
this fix. No manual SQL, no `-v`, no data loss - restart normally and the
next startup log will show `Running upgrade 8b2f5c1e9a44 -> 9c1852419557`.
Verify with `\d climate_records` afterward: a "Check constraints:" section
listing all of the above should now be present.

**Honesty note on verification:** this sandbox cannot install Alembic
(no network access), so this fix could not be run end-to-end here either.
What was verified: (1) the exact 25 constraint names and condition strings
were cross-diffed against `d2616a6f36ac`'s own proven-working versions
with zero discrepancies; (2) both migration files compile cleanly;
(3) `op.create_check_constraint` and `Inspector.get_check_constraints` are
documented, standard Alembic/SQLAlchemy operations, not custom SQL. It has
not been executed against a real PostgreSQL instance by this project -
the log line and `\d` output above are how to confirm it for real on next
restart.


## Follow-up hardening — four small gaps found by re-auditing the project itself

A fresh, deliberate re-audit (not a repeat of the earlier hardening pass's
own list) found four small, non-blocking gaps and fixed three of them; the
fourth turned out, on closer inspection, not to be a gap at all:

1. **`password_reset.py`'s admin listing had no cap.** Same unbounded-query
   pattern as elsewhere, on a table this project's own earlier pass hadn't
   reached. Capped at 200, matching `risk_advisories`.
2. **Considered, then rejected: capping `generate_summary_report_excel()`'s
   risk-advisory sheet to match the PDF's 15-row limit.** These two
   functions are NOT inconsistent by accident - the PDF is a quick-glance
   summary (15 rows, by design) and the Excel export exists specifically to
   give an analyst the complete dataset to pivot themselves. Capping the
   Excel sheet would have broken the one thing it's for. Left unchanged.
3. **The production-hardening pass's own additions (rate limiting, storage
   abstraction, structured logging) had no tests.** `storage_service.py`
   now has 8 tests, each verified by running the identical logic against
   real file I/O in a throwaway directory before being written as pytest
   cases (`tests/test_storage_service.py`).
4. **The CHECK-constraint gap was caught by one person reading one `\d`
   output once - not by anything repeatable.** Two additions close this:
   `tests/test_check_constraints.py` (constraint conditions are logically
   correct, via the existing SQLite test database) and
   `scripts/verify_db_constraints.py` (a standalone script that connects to
   the REAL configured database and confirms all 25 CHECK constraints and
   both unique duplicate-prevention indexes actually exist - cross-checked
   name-for-name against migration `9c1852419557` with zero discrepancies).
   Neither existed when the original gap was found; either would have
   caught it immediately.


## Critical finding — non-root Docker user broke file uploads on any real deployment

Caught live, from a real upload attempt (`PermissionError: [Errno 13] Permission
denied: 'uploads/...'`) after merging the tenth review's non-root-container
fix. Root cause: `chown -R cdr:cdr /app` in the Dockerfile only affects the
image's own build-time layer. `uploads/` is a mounted named volume
(`cdr_uploads`, see `docker-compose.yml`), and a volume's actual on-disk
ownership is whatever it already had - root, for this project's own volume,
since it has existed since long before the `cdr` user did - and mounting it
at container start overrides whatever the image had baked in for that path.
The Dockerfile's own `chown` was therefore correct but irrelevant: it ran
before the volume ever existed at that path.

**Fix:** the container now starts as root (the `USER cdr` instruction was
removed), and `CMD` itself does the ownership fix at the only point it can
actually work - after the volume is mounted, at container start - then
drops to the unprivileged `cdr` user via `su` to run `init_db.py` and
`uvicorn` for the rest of the container's life. The non-root security
benefit is unchanged (the actual running application process is still
`cdr`, never root); only *when* the uploads directory gets its correct
ownership changed, from build-time (wrong, silently a no-op on this
project's real volume) to container-start (right).

This is a direct lesson repeated from the CHECK-constraints finding above:
a fix that is correct in isolation (chown in a Dockerfile is completely
standard) can still be silently wrong against this project's actual,
already-existing deployment state (a volume that predates the fix) - and
the only way that surfaces is by actually running the real thing, not by
reasoning about the Dockerfile in isolation.


## Real gap found through a user's own question — maker-checker had no way to actually check

The user asked directly: why isn't there a way to review each submission's
actual content alongside Approve/Reject, so that data which is technically
VALID (passes every automated check) but suspicious - forged, fabricated -
could still be caught and rejected by a human? Checking the code confirmed
this was a genuine gap, not a misunderstanding: `InternalPortal.tsx`'s
Submission Monitoring table showed only file name, period, status, and
aggregate valid/total counts - no way to see the actual customer/loan/
collateral rows before deciding. The backend already fully supported this
(`GET /submissions/{id}` returns full row-level `records`, and `BOT_USER`
was already an allowed role - `InstitutionPortal.tsx` already used the
identical endpoint for institutions to view their own submissions), so this
was a frontend gap only: the capability existed and was reachable, just
never wired into a button.

**Fix:** a "View Details" button added to each Submission Monitoring row,
opening the same submitted-records table `InstitutionPortal.tsx` already
uses (customer ID, loan ID, amount, collateral, region/district/ward,
hazard, and the automated valid/invalid flag per row), plus the
validation-errors table, with Approve/Reject available directly from that
detail view too. This is exactly what "maker-checker" is supposed to mean:
automated validation catches malformed data, but only a human who has
actually seen the content can judge whether well-formed data is genuine -
a reviewer who could only see a pass/fail count was never actually
checking, only trusting the machine's own verdict a second time.


## User-proposed design improvement — Approve now has real consequence for exported artifacts

The user asked a genuinely good design question after observing that a
VALID-but-not-yet-approved Bank A submission was already contributing to an
Automated Report: if VALID submissions already count everywhere APPROVED
ones do, what does the Approve action actually change? Their own proposal:
keep VALID submissions visible on the live dashboard (fast signal, no
change there), but restrict anything that LEAVES the system as a
standalone artifact - Automated Reports (PDF/Excel/Image/CSV) and a
published Risk Advisory Note's own data_snapshot - to APPROVED submissions
only. Evaluated and agreed: a live dashboard showing a provisional number
is reasonable (BOT gets early signal, and Reject can still retract it
before anyone acts on it), but a PDF handed to someone else, or a
published risk opinion's supporting figures, reads as BOT-confirmed - it
should rest on a number a human actually signed off on, not merely one
that survived automated file-shape checks.

**Implementation:** `_active_records_query()` gained an `approved_only`
parameter (default `False`, preserving every existing caller's behaviour
unchanged). `get_kpi_summary`, `get_hazard_exposure`, and
`get_combined_climate_financial_exposure` now accept and forward it.
`analytics.py` (the live dashboard API) was left untouched - still shows
VALID + APPROVED, by design. `report_service.py`'s three report generators
(PDF/Excel/Image) and `reports.py`'s CSV export now all pass
`approved_only=True` (8 call sites total, verified by exact count before
and after the change). `get_exposure_snapshot` (Risk Advisory's data
source) now hardcodes `approved_only=True` with no toggle - matching the
same "no toggle" pattern this function already used for climate data
(quality_flag == VALIDATED only, always), since a formal archived document
warrants the same certainty on both its financial and climate figures.

Verified with real SQL (SQLAlchemy itself could not be installed in this
sandbox - no network access): a two-submission scenario, one VALID
(1,000) and one APPROVED (5,000), confirmed the dashboard query
(`status NOT IN (PENDING, INVALID, REJECTED, SUPERSEDED)`) totals 6,000
while the report query (`status = APPROVED`) totals 5,000 exactly -
proving the two filters genuinely diverge rather than coincidentally
agreeing.


## Geospatial Overview — final architecture (after extensive iteration)

The map went through many rounds of user-directed redesign - PMO's external
tile layer, convex-hull region outlines, per-district polygon rendering,
dot-density financial layers, checkbox-based multi-hazard color blending,
and a full IDW-interpolated hazard surface - each round driven by specific,
concrete feedback from the user testing the live result. The detailed
round-by-round history (every intermediate attempt, every bug found and
fixed along the way) has been trimmed from this document in favour of the
final architecture below, to keep this matrix readable for review; nothing
about the final design was lost in the trim.

**Final design, as currently shipped:**
- **Hazard layer** (dropdown: Flood/Drought/Landslide/Cyclone, no "All"
  option, default "None" = no layer): renders as a smooth, country-wide
  Inverse Distance Weighting (IDW) surface - the same real spatial-
  interpolation technique published national hazard-mapping studies use
  (e.g. Al-Hemoud et al. 2023, Int. J. Disaster Risk Science, for Kuwait) -
  built in pure JavaScript/Canvas (`buildIdwSurface()` in `HazardMap.tsx`)
  from this project's own `climate_records.hazard_type` exposure per
  region (via the existing `/analytics/hazard-exposure` endpoint - no new
  backend needed), rendered as an `ImageOverlay`. A region with zero
  recorded exposure under the chosen hazard contributes a real zero-value
  anchor point to the interpolation (not simply omitted) - this is what
  makes the surface fade smoothly with distance rather than paint one flat
  color everywhere. PMO's external tile service was evaluated and
  ultimately removed entirely: Combined Climate-Financial Exposure (the
  ICN's core aim) has always been built exclusively from this project's
  own ingested TMA data, and showing PMO's external, disconnected, never-
  independently-verified layer alongside it broke that consistency.
- **Financial layer** (dropdown: Loan/Collateral): renders as small
  (radius 1.4) dots at the ACTUAL latitude/longitude an institution
  entered on its own submitted template for each loan or collateral
  (`get_exposure_points()`/`GET /analytics/exposure-points`, added for
  this purpose - real per-record coordinates, never a region average),
  colored by a linear RGB gradient (pale pink toward red for Loan, pale
  yellow toward gold for Collateral) scaled to that one record's own
  amount.
- **Region name labels**: a light text marker per region (never a filled
  circle), at each region's own centroid.
- **Filtered-region outline**: when Dashboard Filters has a region
  selected, that one region's real boundary is drawn (black, thin) purely
  as a "you are viewing this one" indicator - it never drives hazard or
  financial coloring.
- **Region boundaries** (`frontend/src/data/regionBoundaries.ts`): a
  single clean outer ring per region, built via a concave hull (alpha-
  shape) algorithm - Delaunay triangulation (`scipy.spatial.Delaunay`)
  keeping only triangles below a per-region adaptive alpha threshold, then
  tracing the boundary of their union - over every real district vertex
  from a Tanzania NBS district shapefile the user supplied
  (`Districts.shp`/`.dbf`, 169 districts). This replaced two earlier,
  rejected approaches: a convex hull (mathematically guaranteed to bulge
  in a straight line past any concave section of a region, sometimes into
  a neighbour's territory) and an exact-edge dissolve of the district
  polygons (failed - adjacent districts' shared borders have small real
  digitisation gaps in this dataset, not just floating-point noise, so
  their edges never exactly cancelled at any coordinate precision tested).
  Five external sources for pre-made official boundary data were
  attempted and every one was blocked by that service's own anti-bot
  protections (geoBoundaries/GitHub's Git LFS + robots.txt, HDX's bot
  detection, OSM Nominatim's robots.txt, Overpass API, and ITOS/ArcGIS's
  service not being locatable for Tanzania) - the concave hull built from
  the user-supplied shapefile is the best available result given that.
- Hazard colors are defined once, in `frontend/src/data/hazardColors.ts`,
  and imported by both `HazardMap.tsx` and the Climate Hazard Exposure
  Distribution pie chart on `InternalPortal.tsx`, so the same hazard can
  never render as two different colors in two different places.

## Professional button system - intent-signalling colors across every portal

The user asked to set colors aside for now and focus on making buttons and
layout genuinely professional, given the system will be used by BOT staff.
The concrete gap found: every button on screen - Approve, Reject, Validate,
Flag as Bad Data, Deactivate, Activate, Close, Retry - used the exact same
solid black styling, so a reviewer had no visual cue distinguishing a
confirming action from a destructive one before clicking.

Added a small, consistent button variant system to `index.css` rather than
touching every inline style individually: `.btn-success` (green, Approve/
Validate), `.btn-danger` (red, Reject/Flag as Bad Data/Deactivate),
`.btn-secondary` (outline, Close/Cancel/Retry - a neutral action, always
paired with a stronger sibling rather than standing alone), `.btn-sm`
(compact sizing for buttons inside a table row or dense list, where a
full-size button would visually overpower the row), and a `.button-row`
utility class replacing several pages' own repeated inline
`style={{display:'flex', gap:...}}` for button groups. Also added a visible
`:focus-visible` outline (gold, matching the existing palette) on every
interactive control - a keyboard-navigated, government-facing supervisory
tool needs this and the default browser outline was getting lost against
the dark theme in several places.

Applied across all three portals: Submission Monitoring's Approve/Reject
(both the table row and the detail-view modal), Climate Quality Control's
Validate/Flag as Bad Data, AdminPanel's password-reset Approve/Reject and
its user Deactivate/Activate toggle (color follows the CURRENT state - a
user who IS active shows a red "Deactivate", one who is NOT shows a green
"Activate", so the button's color always previews its own consequence, not
the workflow's general shape), InstitutionPortal's submission-detail Close,
and the Climate Data Quality error banner's Retry.

Also confirmed and can report back to the user directly: this project's
existing color tokens (`--color-primary: #0A0A0A`, `--color-gold: #BB7B02`)
were already sourced from an earlier phase of this project - extracted
directly from Bank of Tanzania's own ICN mockup images (the Concept Note on
the Proposed Enhancement of the Climate Data Repository), per the existing
comment at the top of `index.css` - not a fresh guess made in this round.


## Eleventh review (external) — critical superseding bug fixed, migration made SQLite-portable

An external review of the 26/09/2026 20:43 snapshot correctly identified the
highest-severity remaining issue: `POST /submissions/upload` superseded any
earlier ACTIVE submission (PENDING/VALID/INVALID/APPROVED) for the same
institution+period UNCONDITIONALLY, regardless of the new upload's own
outcome. Concretely: an institution's already-APPROVED, officially-confirmed
submission could be silently retired the moment a correction attempt was
uploaded, even if that correction itself came back INVALID - since INVALID
is excluded from every analytics query, the institution's entire confirmed
dataset for that period would vanish from Combined Exposure and every other
dashboard figure until the correction was fixed and resubmitted, despite
nothing having actually been wrong with the data that had already been
approved. Verified directly against the code (`ACTIVE_STATUSES` and the
unconditional supersede loop in `submissions.py`) before fixing, exactly as
described.

**Fix:** the supersede block now runs only when `submission.status ==
SubmissionStatus.VALID` (computed earlier in the same function, before this
block runs). This closes the gap without opening a different one
(double-counting old and new simultaneously while a correction sits in the
review queue): VALID already counts in every dashboard view alongside
APPROVED (`_active_records_query`'s `EXCLUDED_STATUSES` already excludes
only PENDING/INVALID/REJECTED/SUPERSEDED), and `overall_status` and the
supersede block both execute inside the same request/transaction - so the
instant the old submission is marked SUPERSEDED, the new VALID one is
already active in its place, with no window where neither (or both) count.

The same review also correctly identified that migration `9c1852419557`
(the CHECK-constraint backfill) used `op.create_check_constraint()` calls
directly, unwrapped - which works against this project's production
PostgreSQL target but SQLite does not support adding a CHECK constraint to
an existing table via plain `ALTER TABLE` at all. Fixed by grouping the
constraints per table and applying each table's additions inside
`op.batch_alter_table()`, Alembic's standard mechanism for making such a
migration portable to SQLite (it recreates the table with the constraint
included, copies the data across, and swaps it in) as well as PostgreSQL,
where batch mode is a transparent no-op wrapper around the same direct ALTER
TABLE. `downgrade()` updated to match.

Three further critical findings from the same review - true submission
version-chain fields (`version_number`/`original_submission_id`/
`supersedes_submission_id`), a stricter legacy-schema preflight check, and a
database-level, version-aware `loan_id` uniqueness constraint (genuinely
difficult: `loan_id` lives on `submission_records` while `status` lives on
the parent `submissions` table, so a simple partial/conditional unique index
cannot be applied directly without restructuring) - all require a new
migration (schema change), a materially higher-risk category of edit than
the two logic-only fixes above, and were intentionally paused for the user's
explicit go-ahead before proceeding, rather than bundling further schema
changes into the same pass.


## Twelfth item — true submission version-chain identity (reviewer item #2)

Added `version_number`, `original_submission_id`, and
`supersedes_submission_id` to `Submission` (migration `a1f3d92e6b70`,
`op.batch_alter_table()` for SQLite portability, matching `9c1852419557`'s
own reasoning). Answers the reviewer's exact complaint - "database cannot
say B replaced A, C corrected B, C is current, without relying on
timestamps/status" - directly: `original_submission_id` on any row points
straight to the very first submission in that institution+period's history
(NULL on that first row itself, since it IS the original), and
`supersedes_submission_id` points to the ONE immediately-preceding version.

Populated in `submissions.py` at upload time (right after `db.flush()`,
for EVERY new upload - including ones that turn out INVALID, since an
invalid correction attempt is still real chain history even though it does
not become the active version per the eleventh-review fix above) by
looking up the most recent existing submission for the same institution+
period (ordered by `created_at`, not `version_number` - pre-migration rows
were all backfilled to `version_number=1` and would tie against each
other) and linking off of it. `SubmissionOut` gained the three fields so
API consumers can read the chain without a manual join.

Verified the linking logic directly (three simulated generations: A first,
B correcting A, C correcting B) - confirmed `C.original_submission_id`
resolves all the way back to A (not to B), and `C.supersedes_submission_id`
correctly points to B specifically, matching the exact semantics requested.

Explicitly NOT attempted (paused for the user's go-ahead, given after this
addition): retroactively reconstructing historical chains for submissions
uploaded before this migration ran (the migration backfills
`version_number=1` for every pre-existing row and leaves the two ID columns
NULL - correctly inferring old chains from timestamps/status alone is
exactly the ambiguity this fix exists to stop relying on going forward, not
something to attempt after the fact with the same unreliable signals);
reviewer items #3 (stricter legacy-schema preflight) and #5 (database-level,
version-aware `loan_id` uniqueness - genuinely difficult, since `loan_id`
lives on `submission_records` while `status` lives on the parent
`submissions` table) remain open, along with the eight 🟠/🟡 production-
quality items from the same review (climate `reporting_period` CHECK,
geography master/FK tables, NUMERIC instead of Float for money, DATE
instead of String for dates, structured audit JSON, JSONB advisory
snapshots).


## Thirteenth item — a more complete external implementation adopted in place of the twelfth item's own fix

The user supplied a separately-produced "hardened" version of this project
and asked for it to be reviewed against the outstanding review items.
Comparing it file-by-file against the current project (exactly 6 backend
files plus one migration actually differed - `models.py`, `submissions.py`,
`analytics_service.py`, `validation_service.py`, `schemas.py`,
`risk_advisories.py` - everything else, including this session's own recent
map/analytics/`approved_only` work, matched exactly, confirming it was built
on top of this same codebase rather than an older snapshot) showed a
materially MORE COMPLETE solution to the same versioning problem the
twelfth item above addressed, plus four more review items in the same pass.
Adopted in full, replacing the twelfth item's `a1f3d92e6b70` migration and
its simpler `original_submission_id`/`supersedes_submission_id` fields
(deleted - the two approaches used the same `down_revision`, so keeping
both was never an option; a database can only have one migration chain).

**What makes it more complete, verified directly rather than assumed:**
the twelfth item's fix (and the eleventh item's fix before it) closed the
gap where an invalid correction could retire an already-approved
submission, but neither considered what happens if a VALID correction
(which DOES immediately become the active version) is later REJECTED by
the analyst - simulated this exact sequence (A approved+current, B
uploaded VALID and becomes current while A stops being current, B then
rejected) and confirmed that without a fallback, analytics would go empty
at that point (A no longer current, B now rejected) - the same class of
bug the eleventh/twelfth fixes were meant to close, just occurring one
step later in the workflow. This adopted implementation closes it with an
explicit `is_current` boolean (`Submission.is_current`, checked directly
by `analytics_service.py`'s `_active_records_query` alongside the existing
status-based exclusion) plus fallback logic in the REJECT branch of the
review endpoint: rejecting a submission that was current automatically
reactivates the most recent still-APPROVED submission in that chain as
current again. Verified the full sequence in a standalone simulation:
after B's rejection, A correctly becomes current again - never a gap.

**Also addressed in the same migration** (`b7f2c91d4e60`, all
individually verified against the model/API changes it requires and
against `9c1852419557`'s own SQLite-portability precedent):
- Review item #5 (`loan_id` DB-level uniqueness): a partial unique index
  on `submission_records(submission_id, loan_id) WHERE loan_id IS NOT
  NULL`. Scoped honestly - this hardens the EXISTING within-one-file
  uniqueness check at the database level (a real safety net against that
  specific case slipping through), not the harder, still-open problem of
  version-aware uniqueness across different submission versions for the
  same institution+period (`loan_id` lives on `submission_records` while
  the version/status identity lives on the parent `submissions` table, so
  a simple index cannot express that on its own).
- Review item #7: `ck_climate_records_reporting_period_format` - the same
  YYYY-Qn format check `submissions.reporting_period` already had,
  extended to `climate_records`.
- Review item #10: `risk_advisory_notes.data_snapshot` changed from Text
  to JSON (PostgreSQL only - SQLite's JSON1 support is handled by
  SQLAlchemy's JSON type staying a plain column there). Verified the
  Python side matches: `get_exposure_snapshot()` already returned a plain
  dict, assigned directly to `data_snapshot` with no manual
  `json.dumps()`/`json.loads()` - correct for a JSON-typed column, and
  nothing needed to change in `risk_advisories.py` itself.
- Review item #12: added `disbursement_date_value`/`maturity_date_value`/
  `collateral_pledged_date_value` as real `Date` columns alongside the
  original free-text date columns, backfilled only where the source text
  was unambiguously ISO-formatted (`YYYY-MM-DD`) - ambiguous legacy text is
  left NULL rather than guessed, with the original raw value kept for
  audit.
- Review item #13: the six monetary columns on `submission_records`
  changed from `Float` to `NUMERIC(20, 2)`.
- Backfills existing rows' `version_number`/`previous_submission_id`/
  `is_current` in creation order at migration time (ordered by
  `created_at`) - a different judgment call than the twelfth item's fix,
  which deliberately left historical rows unbacktracked rather than infer
  old chains from timestamps. Both are defensible; this migration's choice
  was adopted along with the rest of the file rather than special-cased.

Not addressed by this migration either: review item #3 (stricter legacy-
schema preflight) and review item #8 (geography master/FK tables) remain
open, along with test coverage for the new versioning/fallback behaviour -
the file-level comparison confirmed no test files changed alongside this
migration.


## Fourteenth item — DB-level "one current version" constraint, with an explicit ICN-scope filter applied

The user supplied a second externally-produced hardened version and, this
time, explicitly asked that only genuinely ICN-relevant fixes be adopted -
not general database-engineering perfectionism beyond what an 8-week
EASTC training prototype demonstrating the ICN Concept Note needs.

**Adopted (migration `c3e4f8a7b901`, plus `models.py`, `submissions.py`,
`analytics_service.py`, `analytics.py`, `audit_service.py`,
`verify_db_constraints.py`):**
- A PostgreSQL/SQLite partial unique index,
  `uq_submissions_one_current_per_institution_period`, guaranteeing at the
  database level that at most one `Submission` can have `is_current = TRUE`
  per institution+reporting_period - closing the review's correctly-
  identified gap that this invariant previously relied on application code
  alone, with no protection against a race condition producing two
  simultaneously-current versions. Pre-existing duplicate `is_current`
  rows are deterministically repaired (preferring the newest APPROVED, then
  newest VALID) before the constraint is added, never silently deleted.
- `submissions.py`'s upload endpoint now catches the `IntegrityError` this
  constraint could raise under a genuine race (two near-simultaneous
  uploads for the same institution+period) and returns a clean HTTP 409
  instead of a raw 500 crash - a database constraint is only safely
  shippable together with the application code that handles it being hit.
- A real refinement to the VALID/APPROVED analytics question the review
  raised (not a new bug, but a genuine improvement on the deliberate design
  from an earlier round of this project - Dashboard shows VALID+APPROVED as
  an "early signal", Reports/Advisory require APPROVED only): a VALID
  submission now only becomes `is_current` immediately when NO APPROVED
  baseline already exists for that institution+period. Once an approved
  baseline exists, a later correction stays provisional (not current) until
  a human reviewer approves it - preserving the fast-signal behaviour for a
  genuinely new period while protecting an already-confirmed baseline from
  being silently displaced by an unreviewed correction. Verified directly:
  simulated all three cases (new period + VALID -> current; existing
  APPROVED baseline + new VALID correction -> NOT current; INVALID upload
  regardless of baseline -> never current) and confirmed each behaves as
  intended.
- `annual_interest_rate` changed to `NUMERIC(8, 4)` (from Float) and
  `audit_logs` gained an additive `details_json` column (existing `details`
  text column untouched) - both bundled into the same migration as the
  constraint fix above, low-risk, and directly used by the audit calls in
  the same file (`details_json={"old_version":..., "new_version":...}` on
  the version-replacement/supersede audit entries).
- `verify_db_constraints.py` extended with entries for the new index and
  column, plus a SQLite-specific fallback (checking `PRAGMA index_list`
  directly) since SQLAlchemy's reflection can miss partial/expression
  indexes on SQLite - a small, directly-tied addition rather than the full
  constraint-registry rewrite the review's item #4 asked for.

**Deliberately NOT adopted, with reasoning given directly to the user as
each was screened against ICN relevance rather than accepted wholesale:**
- Completing `verify_db_constraints.py` into a full auto-generated registry
  from SQLAlchemy metadata (review item #4) - an internal QA script
  improvement, not one of the ICN Concept Note's core functions.
  loan_id"s cross-version uniqueness (review item #3) - the same review
  that raised it said item #2 (adopted above) matters more, since
  correctness already depends on `is_current`, not a raw uniqueness rule.
- Hardening the JSON-migration validation query in `b7f2c91d4e60` (review
  item #5) - a migration-time edge case against malformed JSON that this
  project's own data (synthetic/demo, application-generated) cannot
  actually produce.
- Geography master/reference tables with foreign keys (review item #6) -
  raised across multiple reviews now; this project already validates
  region/district/ward/village against the canonical Tanzania reference
  dataset at the application layer during ingestion, and V2's own migration
  explicitly declines to add hard FKs on the same reasoning ("legacy rows
  with old spelling/casing" would become unmigratable) - a full schema
  normalization is real production-database engineering, not something an
  8-week training prototype's Concept Note calls for.
- Stricter canonical-date rejection for new uploads (review item #7) - a
  validation-strictness enhancement, not a core ICN workflow requirement.


## Fifteenth item — real PostgreSQL runtime bug caught only by actually running the migration

The user ran `docker compose up` against real PostgreSQL and hit a genuine
bug in `b7f2c91d4e60` that neither `py_compile` nor any static review in
this sandbox could have caught, since it is a runtime SQL type-strictness
error, not a Python syntax error: `UPDATE submissions SET is_current = CASE
WHEN id=:chosen THEN 1 ELSE 0 END` - PostgreSQL raised `DatatypeMismatch:
column "is_current" is of type boolean but expression is of type integer`.
SQLite (and MySQL) silently accept `1`/`0` as boolean-ish values; PostgreSQL
does not implicitly cast integer literals to `boolean` in this context.
Every other `is_current` assignment in both `b7f2c91d4e60` and
`c3e4f8a7b901` already correctly used `TRUE`/`FALSE` - this was the one
missed spot. Fixed by changing the literals to `TRUE`/`FALSE`; re-swept
both migration files for the same `1`/`0`-as-boolean pattern afterward and
confirmed zero remaining occurrences.

Separately, before this was reached, the user's own local `alembic/
versions` folder had accumulated two stale files from earlier rounds of
this same session's zips - `a1f3d92e6b70_submission_version_chain.py` (the
first, simpler version-chain attempt, superseded when the more complete
externally-produced `b7f2c91d4e60` was adopted instead) and a
self-generated `9200d8e70f56_fix_multiple_heads.py` (an `alembic merge
heads` the user ran locally to work around the resulting two-heads error,
generated inside an ephemeral `docker compose run` container and never
actually present in this project's own delivered zip). Neither exists in
this project - confirmed directly by listing this project's own `alembic/
versions/` contents (a single clean chain, one head) before troubleshooting
further. Root cause: extracting a new zip on top of an existing folder
only adds/overwrites files present in the zip - it does not delete files
that existed in the destination but are no longer part of the new zip -
so files removed in one round's delivery can silently persist locally
across every subsequent round unless the destination folder is replaced
outright rather than extracted onto repeatedly. Resolved via `Remove-Item`
on the two stale files directly (confirmed by the user's own `dir` output
showing exactly the expected 5 files afterward), rather than requiring a
full folder replacement.


## Sixteenth item — second real PostgreSQL runtime bug in the same migration, also unreachable by static checks

Immediately after the fifteenth item's boolean-literal fix, the user hit a
second, different bug further down the SAME migration
(`b7f2c91d4e60`, line 125): `WHEN disbursement_date GLOB '[0-9][0-9]...'`
- `psycopg2.errors.SyntaxError: syntax error at or near "GLOB"`. `GLOB` is
SQLite-only syntax; PostgreSQL has no `GLOB` function at all (not a
behavioural difference to work around - a hard parse error). The
migration's own guard, `if bind.dialect.name in {"postgresql", "sqlite"}:`,
incorrectly assumed one query body would run on both engines.

Fixed by splitting into two genuinely dialect-specific branches: SQLite
keeps its original `GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'` +
`date(...)` conversion unchanged; PostgreSQL now uses the POSIX regex match
operator, `~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'`, with an explicit `::date`
cast for the conversion itself (PostgreSQL has no `date()` function taking
a text argument the way SQLite does). Verified the regex pattern directly
in Python against five cases before finalizing (`2026-09-25` matches;
`25/09/2026`, `September 25, 2026`, `whatever`, and `2026-9-5` - a
non-zero-padded date - all correctly do not) - the same unambiguous-ISO-
only behaviour the original SQLite `GLOB` pattern intended, now expressed
correctly for PostgreSQL. Also swept both `b7f2c91d4e60` and
`c3e4f8a7b901` for any other SQLite-only functions (`strftime`,
`julianday`, further `GLOB` uses) that might be hiding the same class of
bug - none found; the two occurrences of `GLOB` remaining in the file are
now both correctly confined to the `elif bind.dialect.name == "sqlite":`
branch.

This is now the second genuine PostgreSQL-only runtime bug found in this
same externally-produced migration, in successive attempts to actually run
it - both were the kind of error that only a real database engine can
surface (a Python-level `py_compile` check, which this sandbox can run
without a live PostgreSQL instance, sees a syntactically valid Python
string either way). Recorded plainly rather than glossed over: adopting a
externally-produced migration file, however well-reasoned its logic
appeared on review, still requires it to actually be run against the
target database at least once before it can be called verified - review
and static checks narrow the risk but do not eliminate it.


## Seventeenth item — a real Promise.all-wide dashboard crash, traced back to a file-merge inconsistency

The user reported the Analyst dashboard showing empty everywhere (Submission
Monitoring, Combined Exposure, Geospatial Map, Submission Status
Distribution) despite Institution Portal correctly showing their own 2
submissions (one APPROVED, one VALID) - proving the data genuinely existed
in the database. This ruled out the "you just haven't uploaded anything
yet" explanation offered first (a reasonable read of the initial evidence -
Climate Data Quality was fully populated while every financial section was
empty, and a fresh `SYNTHETIC_SEED` batch timestamp suggested a database
reset - but the user's follow-up showed real submissions existed after all).

**Root cause, traced through `InternalPortal.tsx`'s `loadAll()`:** all
seven of this screen's data fetches run inside a single `Promise.all([...])`
- a JavaScript-level behaviour where ANY ONE rejected promise (e.g. an HTTP
500) causes the ENTIRE combined promise to reject, so NONE of the
`setXxx(...)` calls run - not just the one that actually failed. This
explains why Submission Monitoring (which reads its own list via a
completely separate, unrelated endpoint with no `approved_only` or
`is_current` logic at all) appeared empty too: it was never actually
empty server-side, its own successful response was just never applied to
UI state because a SIBLING request in the same `Promise.all` had crashed.

**The actual crash, found and fixed:** `analytics.py`'s `/map-points` and
`/exposure-points` endpoints pass `approved_only=False` to
`get_region_map_points()`/`get_exposure_points()` - but the current
`analytics_service.py` (adopted from the externally-produced "hardened"
files across the thirteenth/fourteenth items above) had DROPPED the
`approved_only` parameter from both of those two functions' signatures
entirely, while every other analytics function kept it. Calling either
endpoint therefore raised a genuine Python `TypeError` (unexpected keyword
argument) - a real HTTP 500, not a data or logic issue - which is exactly
what `Promise.all` needed to take the whole dashboard down with it.
Confirmed precisely via AST parsing (this sandbox cannot fully import the
module without a live database dependency chain, but `ast.parse` on the
file directly proves the parameter list either does or does not contain
`approved_only`, independent of any runtime environment) that both
functions were missing the parameter before the fix, and correctly have it
after. Fixed by adding `approved_only: bool = False` to both signatures and
threading it through to their own internal `_active_records_query()` (via
`get_hazard_exposure()` for the map, directly for exposure-points) calls -
matching the exact pattern every other analytics function in the file
already used.

**A second, related regression found and fixed in the same investigation
(not itself a crash, but a genuine behavioural bug):** every dashboard
analytics endpoint in `analytics.py` (`kpi-summary`, `hazard-exposure`,
`combined-climate-financial-exposure`, `map-points`, `exposure-points`) was
explicitly passing `approved_only=True` - and three of `analytics_service.
py`'s own function defaults (`_active_records_query`, `get_hazard_exposure`,
`get_combined_climate_financial_exposure`, plus `get_kpi_summary`) had
independently been changed to default to `True` as well. This silently
reversed a deliberate design decision from much earlier in this project
(confirmed, with the user's own explicit input, in the discussion around
the eleventh/twelfth items above): the live dashboard is meant to show
VALID+APPROVED submissions together as an early signal, with ONLY Reports
and Risk Advisory restricted to APPROVED-only. With this regression in
place, the user's own VALID submission would never have appeared on the
dashboard at all, and their APPROVED one would only appear where its
region+period happened to already have matching, also-APPROVED-scoped
climate data - explaining the sparse/empty Combined Exposure and map
specifically, on top of the separate `Promise.all` crash above. Fixed by
changing all five `analytics.py` call sites to explicit `approved_only=
False`, and reverting all four affected function defaults in `analytics_
service.py` back to `False` - re-confirmed `report_service.py`'s own 8
explicit `approved_only=True` call sites (Reports) and
`get_exposure_snapshot()`'s hardcoded `approved_only=True` (Risk Advisory)
were untouched by either regression and remain correctly APPROVED-only.

This is the third genuine bug found only by the user actually running the
adopted "hardened" files against a live system (after the two PostgreSQL
migration bugs in the fifteenth/sixteenth items) - and, unlike those two,
this one was not a SQL-dialect portability issue but a plain file-merge
inconsistency: different rounds of externally-produced files, adopted
separately across this session, had drifted out of sync with each other on
a parameter that several files needed to agree on simultaneously.


## Eighteenth item — two High-severity gaps found while writing the SRS, fixed

Verifying the Software Requirements Specification against the source found two
High-severity gaps. Both are now fixed in code.

**KG-13 — the production guard on `SECRET_KEY` did not cover the values the project
actually ships.** `main.py` refused to start with `ENVIRONMENT=production` only when
`SECRET_KEY == "change-me"`. Docker runs with the fallback in `docker-compose.yml`
(`change-this-to-a-long-unique-secret-before-production-use`) or, if the sample file is
copied as-is, the one in `.env.docker.example` (`change-me-to-a-long-random-secret`).
Neither equals `change-me`, so the backend started in production with a signing key
that is public in the repository, and access tokens could be forged. The comment in
`docker-compose.yml` claimed the opposite. Confirmed by running the old condition
against the shipped values: it blocked 1 of 3.
*Fix:* `app/core/startup_checks.py` rejects, in production, an empty key, any key
containing a placeholder fragment (`change-me`, `change-this`, ...) and any key shorter
than 32 characters; the environment name is matched case-insensitively (`Production`
previously bypassed the guard). `main.py` calls it at start-up; the HSTS check uses the
same case-insensitive test. The compose and `.env.docker.example` comments were corrected.
**Operational note:** a production deployment that currently uses a short or placeholder
key will now refuse to start until a real key is set
(`python -c "import secrets; print(secrets.token_hex(32))"`).

**KG-02 — deactivating an institution did nothing to its users.** The endpoint set
`Institution.is_active = False`, but login, token refresh and per-request authentication
checked only the *user's* flag, so users of a deactivated institution could still sign in
and upload.
*Fix:* `app/core/account_status.py` decides whether a user may authenticate: the account
and, for institution users, the owning institution must both be active (only an explicit
`False` on the institution blocks - a legacy NULL does not lock anyone out). It is used by
`get_current_user` (so already-issued access tokens stop working), by login (a distinct
message, given only after the password is verified, so usernames cannot be enumerated), by
token refresh, and by password recovery (no request is created for such a user). BOT
Analysts and System Administrators have no institution and are unaffected.
Because deactivation now has real consequences, `PATCH /api/institutions/{id}/activate`
was added (System Administrator only, audited as `INSTITUTION_ACTIVATED`) so access can
be restored without editing the database.

**Verification, stated honestly.** The pure logic of both fixes was executed here against
the real shipped values and a six-case account matrix (all as expected). `tests/
test_startup_checks.py` (9 functions): 17 of its 18 parametrized cases were executed and
passed; the 18th needs `pydantic_settings`, not installed in this environment.
`tests/test_institution_deactivation.py` (10 functions) drives the real API and needs the
full stack: it was **written but not executed** - run `docker compose exec backend pytest -v`
before relying on it.


## Nineteenth item — the automated suite was run for the first time; three root causes found and fixed

The user ran `docker compose exec backend pytest -v` for the first time in this
project's history (every earlier "117/136 tests" figure in this document was a
static count of test functions, never a confirmed pass). Result: 91 failed, 53
passed, 1 skipped. Read through the full failure output and traced every
distinct failure back to exactly three root causes, all now fixed in code -
**none of them in the KG-02/KG-13 fixes from the previous item**, which the
analysis below confirms were themselves only victims of the first root cause.

**Root cause 1 (the large majority of the 91 failures): the shared rate
limiter was never reset or disabled for tests.** `app/core/rate_limit.py`'s
`limiter` is a module-level singleton wired into `app` once at import time; it
is never recreated per test. With roughly 300 `login()` calls across the whole
session against the 10/minute login limit, tests later in the run received
HTTP 429 instead of the response they were actually testing - surfacing as
`KeyError: 'access_token'` (login itself 429'd) or, in a few tests, a direct
`assert 429 == 403` where the test's own expected status collided with the
limiter firing first. This explains the near-entirety of the failures in
`test_climate_ingestion.py`, `test_password_policy.py`, most of
`test_rbac_and_isolation.py` and `test_upload_and_workflow.py`, and - notably
- every single failure in the brand-new `test_institution_deactivation.py`
written for the previous item's KG-02 fix. That is genuinely reassuring: it
means KG-02's application code was never actually exercised incorrectly, only
blocked from running at all.
*Fix:* `tests/conftest.py` sets `limiter.enabled = False` once, confirmed (by
searching the test sources) that no test in the suite asserts on 429 itself,
so this is safe for the whole session rather than needing a per-test reset.
**Caveat stated plainly: this sandbox has no `slowapi` installed (no network
access to install it), so this could not be executed here.** The `.enabled`
flag is slowapi's own documented way to disable it for tests; it was applied
based on that, not verified by running it.

**Root cause 2: two test helpers construct `Submission` rows directly
(bypassing the upload API) without setting `is_current`.** `Submission.
is_current` defaults to `False` on the model (correct for production - a
freshly-inserted row should not silently become authoritative). The real
upload endpoint sets it correctly as part of the version-chain logic
(thirteenth item above); these two helpers pre-date that logic and were never
updated, so every submission they created was invisible to
`_active_records_query` (`is_current == True` required) - explaining the
`0.0`/`0` vs. expected-amount assertion failures and every `StopIteration` in
`test_combined_exposure_quality.py` (searching a result list for a region that
was never actually in it).
*Fix:* `_seed_status_submission()` in `test_analytics_submission_status.py`
now sets `is_current = status in (VALID, APPROVED)` - matching BR-06 exactly,
rather than always-True, since this specific test's whole point is proving
PENDING/INVALID stay excluded. `_seed_submission_for()` in
`test_rbac_and_isolation.py` (also imported by
`test_combined_exposure_quality.py`) now sets `is_current=True`
unconditionally, correct there since it always constructs a VALID submission
with no prior version for that institution+period.

**Root cause 3: `_seed_submission_for()`'s generated username collided when
called twice for the same institution.** It built the submitting user's
username as `submitter_{institution.code}` - fine for a single call, but two
tests (`test_exposure_snapshot_hazard_filter_uses_real_climate_data`,
`test_kpi_summary_can_be_narrowed_by_region`) call it twice against the same
institution (once per region, to compare two submissions), producing a
`UNIQUE constraint failed: users.username` `IntegrityError` on the second
call.
*Fix:* an `itertools.count()` module-level counter is appended to the
username, giving every call its own identity regardless of how many times
it is invoked for the same institution.

**Verified here, and what was not:** the root-cause diagnosis for causes 2
and 3 was confirmed by grep against every failing test's actual source (which
helper it calls, how many times, and against `Submission.is_current`'s real
model default) - not guessed. All three fixes compile cleanly. **The suite
was not re-run after these fixes** (this sandbox has no `pytest`/`fastapi`/
`sqlalchemy` installed) - `docker compose exec backend pytest -v` needs to
be run again to confirm 91 failures actually clear, particularly to confirm
the `slowapi` `.enabled` attribute behaves as expected in the real
environment.


## Twentieth item — full test run after the nineteenth item's fixes: 91 to 4, then 4 real bugs found and fixed

The user rebuilt the containers and ran the suite again: 91 failed -> 4 failed,
140 passed, 1 skipped (145 total; two new test modules from earlier items
brought the count up from 136). This confirms the nineteenth item's three
root causes (shared rate limiter, missing `is_current` in two seeding
helpers, a username collision) were diagnosed correctly, including
`slowapi`'s `.enabled` flag actually working as expected in the real
environment - unverifiable in this sandbox at the time, now confirmed.

The remaining 4 failures were new findings, read from the actual pytest
output and traced to two further root causes - one a test-data modelling
issue, one a genuine, serious application bug.

**Test-side (2 failures): two tests seed two Submission rows, both
is_current=True, for the SAME institution+reporting_period.**
`test_exposure_snapshot_hazard_filter_uses_real_climate_data` and
`test_kpi_summary_can_be_narrowed_by_region` each call
`_seed_submission_for()` twice for one institution (once per region, to
compare two regions' exposure) - both calls set `is_current=True`
unconditionally, which the fourteenth item's partial unique index
(`uq_submissions_one_current_per_institution_period`) correctly rejects:
two simultaneously-current submissions for the same institution+period is
exactly the situation that constraint exists to prevent, real upload or
test data alike.
*Fix:* `_seed_submission_for()` now checks for an existing current
submission for that institution+period first; if one exists, it appends the
new loan as another `SubmissionRecord` row on that SAME submission instead
of creating a second competing one - the realistic shape (a real
institution's quarterly file already covers every region it lends in, as
rows within one file, not as several separate submissions) and exactly
what both tests actually needed (their assertions sum exposure across
regions; neither counts submissions).

**Application-side (2 failures, one root cause): the upload endpoint
inserted the new current submission BEFORE demoting the old one.**
`submissions.py` built the new `Submission` with `is_current` already
computed, called `db.add(submission)` then `db.flush()` immediately to
obtain its id - and only AFTER that flush did it query for and demote any
existing current submission for the same institution+period. For an
instant inside that flush, both the old and the new submission were
`is_current=True` at once, which the same partial unique index correctly
rejected - turning `IntegrityError` into `HTTPException(409)` on every
second VALID upload for an institution+period that already had a current
one. This broke the exact workflow the version-chain redesign (thirteenth/
fourteenth items) exists to support: `test_new_upload_supersedes_
previous_submission_same_period` (a second, distinct-loan-id VALID upload
for the same period, expecting 201) and
`test_duplicate_loan_id_within_same_file_flagged` (expecting 201 with
status INVALID) both got 409 instead.
*Fix:* the demotion of any existing current submission (its own query,
audit entries, and an explicit `db.flush()`) now runs BEFORE the new
`Submission` object is even constructed, so by the time it is inserted the
old one is already `is_current=False` in the same transaction - never both
`True` at once. Verified with a standalone simulation of four sequential
uploads (three VALID, one INVALID) asserting "never more than one current
row" after every step: passed.

**A second root cause, found investigating the duplicate-loan-id failure
specifically: `uq_submission_records_submission_loan` (thirteenth item) was
never scoped to valid rows.** A file with a duplicate loan_id is meant to
be storable as INVALID - the application already flags the repeated *row*
(`validation_service.py`'s `seen_loan_ids` check marks only the second and
later occurrences `is_valid=False`, confirmed by reading that logic
directly; the first stays valid), and FR-SUB-07 requires every submitted
row to be persisted for the reviewer to see, including the flagged one.
The index as it stood (partial on `loan_id IS NOT NULL` for PostgreSQL,
not partial at all for SQLite - neither variant excluded invalid rows)
still blocked storing that second, already-correctly-flagged row, so the
INSERT itself failed with `IntegrityError` -> 409, discarding all row-level
validation feedback on every duplicate-loan-id upload rather than only a
genuine defect.
*Fix:* rebuilt as `WHERE loan_id IS NOT NULL AND is_valid = true` on both
engines - migration `e7a1f4c9b382`, and the equivalent change in
`models.py`'s own `Index()` declaration, which matters independently here:
this project's tests build their schema via `Base.metadata.create_all()`
directly from `models.py`, not through Alembic, so the model declaration
governs what the test suite actually runs against; the migration is what
carries the fix to an already-deployed database. Confirmed the fix is
sufficient by reading the validation logic precisely: only ever one row per
duplicated loan_id stays `is_valid=true` within one submission, so the
partial index can never find two rows to conflict on for that reason again
- while a genuine defect that let two BOTH-valid rows share a loan_id
(which should never happen) would still be caught.

**Verified here:** the reordering logic (four sequential uploads) and the
"only one row keeps is_valid=true per duplicated loan_id" reading of
`validation_service.py`, both directly. All five changed/added files
compile. **Not verified:** the suite was not re-run (still no `pytest`/
`fastapi`/`sqlalchemy`/`slowapi` in this sandbox) - run `docker compose
down`, rebuild, `up`, then `pytest -v` again to confirm 145 pass.


## Twenty-first item — full suite run after the twentieth item's fixes: 4 to 1, then closed

The user rebuilt and ran the suite a third time: 4 failed -> 1 failed, 143
passed, 1 skipped (145 total). Three of the twentieth item's four fixes are
now directly confirmed correct by a real pytest run (the sequential-upload
reordering, the duplicate-loan-id partial index, and the region-narrowing
seeding change). The one remaining failure was a distinct, fourth issue that
the earlier IntegrityError had been masking.

**`test_exposure_snapshot_hazard_filter_uses_real_climate_data`: the only
`get_exposure_snapshot()` test that asserts a real exposure figure, seeded
through a helper that only ever produces VALID submissions.**
`get_exposure_snapshot()` (used exclusively for Risk Advisory Notes) is
correctly, deliberately restricted to `Submission.status == APPROVED` and
nothing else, by design (BR-09: a published advisory rests on confirmed
figures, not merely automated-validation-passed ones) - confirmed by
reading `_active_records_query()`'s `approved_only=True` branch directly,
which checks status alone and does not require `is_current` at all on that
path. `_seed_submission_for()` (used by this test, via the twentieth item's
own fix) only ever creates `VALID` submissions, so this specific
assertion could not have passed regardless of the is_current/uniqueness
fixes already applied - the two other `get_exposure_snapshot()` tests in
the same file happen to pass regardless because they only assert on the
attached climate reading, never on the exposure amount that the
`approved_only` restriction actually gates.
*Fix:* test-side only. The test now explicitly sets the shared submission's
`status = SubmissionStatus.APPROVED` before committing (both seeding calls
return the same underlying submission, per the twentieth item's
append-when-current-exists change, so one status change covers both
regions' rows). Verified directly against `_active_records_query()`'s
source that `approved_only=True` needs status alone, confirming this is
sufficient; the `db_session` fixture rebuilds tables per test, so mutating
this one submission's status cannot affect any other test.

**Not itself changed:** `get_exposure_snapshot()`'s APPROVED-only
restriction is correct and was not weakened - this was a test-data gap, not
an application defect.

**Suite status: all fixes from the nineteenth, twentieth and this item are
now confirmed by an actual, complete pytest run reported by the user - 145
collected, 1 skipped (the shipped-secrets check that needs the repository
root files, not available inside the container), and, pending this last
fix, 144 passing.** This is the first point in the project where the
automated suite's state is verified rather than inferred.


## Twenty-second item — full suite confirmed green

The user ran the suite a fourth time after the twenty-first item's fix:
**144 passed, 1 skipped, 0 failed** (145 collected). The single skip is
`test_every_secret_placeholder_shipped_in_the_repository_is_rejected_in_production`,
which needs `docker-compose.yml`/`.env.docker.example` at the repository
root - not present inside the backend container's filesystem, so it skips
itself by design rather than failing; this is expected and correct.

This closes the chain of six items (seventeenth through twenty-second)
that began with the user's first-ever real run of this project's automated
suite (91 failed, out of what had until then only ever been a static count
of test functions). Every fix along the way - the shared rate limiter, two
`is_current`-blind seeding helpers, a username collision, the demote-
before-insert ordering bug in the upload endpoint, the loan-id uniqueness
index not scoped to valid rows, and the final Risk-Advisory seeding gap -
is now confirmed correct by an actual, complete, green pytest run reported
directly by the user, not by static reading or standalone simulation alone.

The project's test count stands at 145 (up from the 117 last independently
verifiable count before this chain of fixes began), across 13 backend
modules, run automatically by GitHub Actions on every push and pull request
to `main` (NFR-MNT-02).


## Twenty-third item — external code review (10 findings), all confirmed and fixed

An independent external review of the codebase (the version delivered after
the twenty-second item) raised 10 findings. Each was verified directly
against the source before any change was made; all 10 were confirmed real.
Fixed:

1. **Health endpoint leaked the raw database exception** (`main.py`) - could
   expose hostname, driver or credential details to any unauthenticated
   caller. Now logged server-side only; the response says `"unreachable"`.
2. **Production start-up did not validate `DATABASE_URL`**, only `SECRET_KEY`
   - an operator could set a real signing key yet leave the database on its
   `docker-compose.yml` default (`cdr_dev_only_change_me`) and still start in
   production. `startup_checks.py` gained `insecure_database_url_reason()`
   (placeholder markers, `sqlite`, `localhost`), wired into the same
   `enforce_production_secret()` call in `main.py`. Verified directly against
   the real shipped default.
3. **Climate ingestion had no row-count ceiling**, unlike the financial
   submission validator (`MAX_UPLOAD_ROWS` existed in config but was never
   read by `parse_and_validate_climate_file()`). A compressed XLSX could
   decompress far beyond the file-size check. Added the same `max_rows`
   enforcement pattern as submissions, plus a column-count ceiling
   (`MAX_CLIMATE_UPLOAD_COLUMNS = 60`) against a pathologically wide file.
4. **(same root cause as 3)** - closed by the same fix; no separate change
   needed once the row/column ceilings exist.
5. **Dashboard analytics include VALID as well as APPROVED data with no UI
   disclosure.** The backend behaviour itself is intentional (BR-09: live
   dashboards are a deliberate early-signal view; reports and exports are
   already APPROVED-only) - confirmed by design, not changed. What was
   missing was telling the viewer this on the dashboard itself: added an
   explicit banner above the KPI cards in `InternalPortal.tsx`.
6. **SYSTEM_ADMIN has no analytics access** - the reviewer\'s own conclusion
   was that this matches the documented role-separation design (Section 3.3
   of the SRS) and should not be changed without a BOT decision. No action
   taken.
7. **The login page always displayed demo credentials**, regardless of
   environment, even though `init_db.py` already correctly skips seeding
   demo accounts in production. `/api/health` now reports a coarse
   `environment` label (not a secret); `Login.tsx` fetches it on mount and
   shows the demo-credentials panel only when it is not `"production"`.
8. **Login lockout status was revealed before the password was checked** -
   any password against a locked account produced a distinct 403, so an
   attacker could confirm a username was valid and currently locked without
   ever supplying its correct password, contradicting the endpoint\'s own
   "never reveal which one it was" comment. Reordered so the lockout message
   is reachable only after the correct password has been verified; a wrong
   password now always produces the same generic 401, locked or not.
9. **`GET /risk-advisories` hard-capped at 200 notes with no way to reach
   older ones.** Given the same optional-pagination shape `GET /submissions`
   already uses (`page`/`page_size`, `X-Total-Count` header, plain array
   either way) so the existing dashboard call is unaffected.
10. **`GET /climate-data/ingestions` hard-capped at 100 batches**, same gap
    and same fix as item 9.

**Verified here:** items 2 and 3 were exercised directly against real values
(the shipped `docker-compose.yml` default; a synthetic oversized CSV) with
matching results. All ten fixes compile; the full AST call-signature
cross-check (Section, twelfth item\'s method) found zero mismatches
afterward. Item 8\'s existing lockout test
(`test_account_locks_after_max_failed_attempts`) was confirmed still valid
under the new ordering by tracing it by hand, since it already used the
correct password on its final, lock-revealing attempt. **Not executed:**
every new test that needs the full FastAPI/SQLAlchemy stack (all except the
pure-logic `test_startup_checks.py` additions) - this sandbox still has
neither package. Run `docker compose exec backend pytest -v` to confirm.


## Twenty-fourth item — full suite confirmed green after the external review fixes

The user rebuilt and ran the suite again: **169 passed, 2 skipped, 0 failed**
(171 collected, up from 145). All ten fixes from the twenty-third item are now
confirmed correct by an actual run, including everything that could only be
compile-checked, not executed, in the sandbox that wrote them: the health
endpoint's exception-leak fix and its new `environment` field, the climate
ingestion row/column ceilings, both new pagination endpoints, and - most
load-bearing of the ten - the login lockout reordering (three new tests
specifically proving a wrong password against a locked account now returns
the same generic response as an unknown username, closing the enumeration
channel item 8 identified).

Both skips are by design: `test_the_shipped_docker_compose_default_is_rejected_directly`
and `test_every_secret_placeholder_shipped_in_the_repository_is_rejected_in_production`
each need `docker-compose.yml`/`.env.docker.example` at the repository root,
which is not present inside the backend container's filesystem, and each
calls `pytest.skip()` for exactly that reason rather than failing.

Test count: 171 (up from 145 at the twenty-second item), across 16 backend
modules.


## Twenty-fifth item — official decision: dashboards and exports are APPROVED-only (BR-09 restated)

The user made a deliberate design decision, stated directly: institution data
that validates successfully (VALID) should remain visible in the system - its
own status, the institution's submission history, the BOT Analyst's
Submission Monitoring queue - but must not be included in any calculation
("manipulated": aggregated, charted, exported, or advised on) until a BOT
Analyst has approved it. This retires the previous "early signal" design,
where live dashboards counted current VALID data alongside APPROVED data
(reports and risk advisories were already APPROVED-only).

**Implementation.** `_active_records_query()` in `analytics_service.py` - the
single query every analytics function is built on - now requires
`Submission.is_current == True AND Submission.status == APPROVED`
unconditionally. The `approved_only` parameter that previously toggled
between the two modes was removed entirely, from every function signature
and every call site (`analytics.py`, `reports.py`, `report_service.py`), so
the old ambiguity cannot be silently reintroduced by a future call passing
the wrong flag - there is now only one behaviour.

**A related defect this change exposed and fixed in the same pass:**
approving a corrected version retires the previous current version
(`is_current = False`) but was never changing that previous version's own
`status` away from APPROVED. `_active_records_query()`\'s old APPROVED-only
branch (used until now only by reports and risk advisories) checked `status`
alone, with no `is_current` check - so a retired-but-still-APPROVED version
could have been double-counted alongside its replacement for the same
institution and period. Verified directly with a standalone simulation
(seed v1 APPROVED+current, approve a correction v2, confirm v1 is excluded by
`is_current` despite still reading `status == APPROVED`): confirmed the fix
closes it. The new query requires both conditions together everywhere.

**Test changes.** `_seed_submission_for()` in `test_rbac_and_isolation.py`
now defaults to APPROVED instead of VALID (its `status` parameter was
present but silently unused before this pass - a leftover from an earlier,
incomplete edit - and is now correctly wired through). Every existing caller
of that helper needed no changes beyond this default. Three tests needed
rewriting because their own assertions depended on the retired VALID-counts
behaviour: `test_pending_and_invalid_submissions_do_not_enter_exposure_
analytics` (renamed to `test_only_approved_submissions_enter_exposure_
analytics`, with an APPROVED case added); `test_new_upload_supersedes_
previous_submission_same_period` (rewritten to approve both versions in
turn, which now also directly exercises the double-counting fix above); and
one stale docstring in `analytics_service.py` describing the retired
distinction between dashboards and risk advisories.

**Frontend.** The KPI-section banner in `InternalPortal.tsx` was rewritten
from a "these figures may include unapproved data" warning to a plain
confirmation that all figures are BOT-approved.

**SRS.** BR-09, FR-ANA-04, Section 3.2.8's narrative, AC-07, R-01, the
Appendix G index entry, and the Section 5.3/5.4 coverage notes were all
restated to match, versioned as 1.3.

**Verified here:** the double-counting fix via standalone simulation
(confirmed correct); the full AST call-signature cross-check (zero
mismatches after removing `approved_only` from every signature and call
site); full backend compile. **Not executed:** the rewritten and new test
assertions need the full FastAPI/SQLAlchemy stack, still unavailable in this
sandbox - run `docker compose exec backend pytest -v` to confirm the full
171-test suite still passes under the new behaviour.


## Twenty-sixth item — first real run under APPROVED-only analytics: 2 failures, both fixed

The user ran the suite immediately after the twenty-fifth item's APPROVED-only
change: 167 passed, 2 skipped, 2 failed (171 collected). Both failures were
new findings from this specific change, read from the real pytest output and
fixed - one a genuine defect in application code the change newly exercised,
one a mistake in a test written for the twenty-fifth item itself.

**Application defect (found by the test, not by inspection): the REVIEW
endpoint's APPROVE and REJECT branches had the same demote-before-promote
ordering hazard already fixed once in the UPLOAD endpoint (twentieth SRS
item).** `review_submission()`\'s APPROVE branch set `old.is_current = False`
for the previous current version and `submission.is_current = True` for the
newly-approved one as two plain ORM attribute mutations with no flush between
them, both committed together at the end of the function. SQLAlchemy's
unit-of-work does not guarantee which UPDATE it emits first in that
situation - if it wrote the new row's `is_current = True` before the old
row's `is_current = False`, both were briefly `is_current = True` at once,
which the same partial unique index the upload-path fix protects against
correctly rejected, turning a routine second approval (approve version 1,
later approve a correction version 2) into an `IntegrityError`. This path had
never been exercised before: no existing test approved two different
versions of the same submission in sequence until
`test_new_upload_supersedes_previous_submission_same_period` was rewritten
for the twenty-fifth item specifically to prove the earlier double-counting
fix - which is exactly the test that hit it. The REJECT branch's fallback-
restoration (`fallback.is_current = True` after `submission.is_current =
False`) had the identical latent hazard, unexercised by any existing test;
fixed proactively in the same pass rather than waiting for it to surface
separately.
*Fix:* both branches now call `db.flush()` immediately after demoting the
old current version(s), before promoting the new one - mirroring the
upload-path fix exactly. Verified with a standalone simulation covering
upload, approve-then-approve, and reject-with-fallback in sequence, checking
"at most one current row" after every individual mutation (not just at the
end): all three sequences passed.

**Test defect (in the twenty-fifth item's own new test, not application
code): `test_only_approved_submissions_enter_exposure_analytics` seeded
PENDING, INVALID, VALID and APPROVED submissions for the institution's SAME
reporting period.** Since VALID and APPROVED are both eligible to be
`is_current` (BR-06), and the database allows at most one current submission
per institution+period, seeding a current VALID and a current APPROVED row
for the identical period is a state a real institution could never reach -
the test was asserting an impossible combination.
*Fix:* each seeded status now gets its own reporting period (2026-Q1 through
Q4); `get_hazard_exposure()` aggregates across all periods for an
institution when no period filter is given, so the test's assertion (only
the APPROVED period's amount is counted) is unaffected by the change and now
reflects a state that can actually occur.

**Verified here:** the three-sequence simulation above, run directly. Full
backend compile clean; both fixed files compile. **Not executed:** the
corrected test file and the fixed endpoint need the full FastAPI/SQLAlchemy
stack, still unavailable in this sandbox - run `docker compose exec backend
pytest -v` to confirm all 171 collected tests (169 passing + 2 by-design
skips, matching the twenty-fourth item's count) pass again under both this
fix and the twenty-fifth item's APPROVED-only decision together.


## Twenty-seventh item — hazard layer did not localize to the Dashboard Filters' region selection

The user selected Dodoma in Dashboard Filters, confirmed the financial
(Loan/Collateral) map layer correctly narrowed to Dodoma's own points, then
selected the Flood hazard layer and found it painted the entire country in
solid blue instead of showing a hotspot over Dodoma the way the financial
layer had just done - asking for the hazard layer to follow the dashboard
filter the same way.

**Root cause, confirmed mathematically before any code change:** `HazardMap.
tsx` built its IDW input list (`dataPoints`) directly from the `points` prop
- the SAME region-centroid list also used for the map's circle markers, which
is correctly re-fetched from `/analytics/map-points` WITH the active
`filter_region` whenever Dashboard Filters changes (so the circle markers
correctly show only Dodoma when Dodoma is selected). But Inverse Distance
Weighting mathematically requires at least one ZERO-VALUE anchor elsewhere to
interpolate a gradient against - with only ONE point in `dataPoints` (Dodoma,
once the filter narrowed the list to it), IDW's weighted average reduces to
that single point's exact value at every pixel on the canvas, with no
distance decay at all: the whole map is painted one solid colour. Verified
directly with a standalone simulation of the real formula: with only Dodoma
as input, Dodoma's own coordinate and Dar es Salaam's (hundreds of km away)
returned the IDENTICAL value; with all six of the demo dataset's regions
included as anchors (only Dodoma non-zero, matching what the filtered
hazard-exposure query actually returns), the same two locations returned
5,000,000 and 9.6 respectively - a properly localized, decaying hotspot.

**Fix:** `HazardMap.tsx` now fetches a SECOND, always-unfiltered region-point
list (`allRegionPoints`, via a plain `/analytics/map-points` call with no
query parameters, fetched once and cached) used ONLY to build the IDW anchor
coordinates. The VALUE at each anchor still comes from `hazardAmountByRegion`,
itself built from `hazardRows` - which correctly continues to respect every
Dashboard Filter (region, institution, period) exactly as before. The
`points` prop (filtered) is untouched and still drives the circle markers,
which should and do continue to narrow to the selected region. Net effect:
selecting Dodoma now shows hazard exposure concentrated over Dodoma,
decaying with distance, with the underlying value itself still scoped
exactly to what the filter asked for - not a nationwide flat fill and not
unfiltered data either.

**Verified here:** the exact IDW formula (haversine distance, power=2.2,
weighted average) run standalone in Node.js against real Tanzania region
coordinates, both before and after, with results matching the reported
symptom precisely and confirming the fix's effect precisely. Brace/paren
balance of the edited file confirmed. **Not executed:** this is a frontend
(TypeScript/React) change; no TypeScript compiler or dev server is available
in this sandbox to build or render it. Rebuild the frontend
(`docker compose up --build`) and visually confirm the Flood layer now
concentrates over Dodoma when Dodoma is the selected Dashboard Filter.


## Twenty-eighth item — intermittent browser freeze when both map layers are active together

The user reported the map "stacks" (freezes) when both a hazard layer and a
financial layer are selected together on the dropdowns - not every time.

**Root cause, found by inspection of the render path (not yet reproduced
directly - see verification note below):** the financial layer renders one
React `<CircleMarker>` (with its own `<Tooltip>` child) per point returned by
`GET /analytics/exposure-points`, which caps at 20,000 points per category
(`get_exposure_points()`'s own documented `limit`). Each `CircleMarker` was
an individual SVG DOM element by default (react-leaflet's default renderer).
A narrow Dashboard Filter (few institutions/one period) returns few points
and renders instantly; a broad filter ("all institutions") against
bulk-uploaded test data (this project has 16,000-31,000-row test files on
record) can return thousands of points, and creating thousands of SVG
elements in one render pass - at the same moment the hazard layer's IDW
surface is also computing a 140x140 grid, each cell summed over every anchor
region - is enough main-thread work to freeze the tab. This matches the "not
every time" report precisely: it depends on how much data the current filter
selection actually returns, not on a fixed code path.

**Fix:** added `preferCanvas={true}` to the `MapContainer` in `HazardMap.
tsx`. This is a standard, documented Leaflet/react-leaflet option that
switches vector layers (CircleMarker, Polygon) to a single shared `<canvas>`
element instead of one SVG node per marker - the standard fix for exactly
this class of "thousands of Leaflet markers freeze the browser" problem,
with no change to what data is fetched, shown, or how tooltips/hover
behave.

**Verification, stated plainly - this item's evidence is weaker than usual.**
Every prior fix in this project was at least confirmed by a standalone
logic/math simulation reproducing the exact reported symptom. This one was
not: reproducing a real browser-rendering freeze needs an actual browser
with thousands of real data points loaded, which this sandbox cannot run.
What WAS done: brace/paren balance confirmed on the edited file (139/139,
209/209); the JSX structure was read by hand to confirm the added comment
and prop are both syntactically valid; `npm install` was attempted to get a
real `tsc --noEmit` type-check against react-leaflet's actual types, but
this sandbox's npm registry access returned 403 Forbidden even for a single
lightweight package, so no compiler-verified check was possible.
`preferCanvas` is a genuine, documented option on react-leaflet v4's
`MapContainer` (the version pinned in this project) from training knowledge,
not from reading the installed type definitions directly. Rebuild the
frontend and confirm directly: select a broad filter with many points
alongside a hazard layer and confirm the map no longer freezes, and that
markers/tooltips still behave exactly as before.


## Twenty-ninth item — admin-side review: four findings, all fixed

A focused review of the System Administration side (AdminPanel.tsx, users.py,
institutions.py, password_reset.py) found four real gaps.

**1. No UI to activate/deactivate an institution, despite the backend fully
supporting it.** The Institutions table showed Code/Name/Type/Status with no
action column at all - unlike the Users table, which already had
Activate/Deactivate. Since institution deactivation now has real effect
(KG-02, closed earlier: it blocks every user of that institution from
signing in), an administrator had no supported way to trigger it, or to
reverse it, without calling the API directly. *Fix:* added a Deactivate/
Activate button per institution, with a confirmation prompt on deactivation
specifically (since it cascades to every user of that institution, unlike
deactivating one user) and error surfacing on failure - `toggleUserActive`
gained the same error handling for consistency.

**2. KG-03 (recorded as an open gap since the eighteenth item, never
fixed): an administrator could deactivate the own account, or the last other
active administrator, locking the whole system out of administration.**
*Fix:* `deactivate_user()` now refuses both cases with a clear reason
(self-deactivation; last-active-admin), verified with a standalone
simulation of all four relevant combinations (self, another admin with a
third remaining active, the actual last admin, a non-admin role) before
being implemented as five new tests in `test_admin_self_lockout.py`.

**3. `UserCreate` had no validation linking `role` and `institution_id`.**
An INSTITUTION_USER could be created with no institution at all - a
silently broken account with no tenant scope, since every institution-scoped
query depends on it being set - and a BOT_USER or SYSTEM_ADMIN could be
given one it would never use. *Fix:* `create_user()` now requires an
institution for INSTITUTION_USER, forbids one for every other role, and
confirms a supplied institution id actually exists; six new tests in
`test_user_creation_validation.py` cover both roles and the valid/invalid
cases. The "Add New User" form was updated to match: the institution
selector is now shown (and required) only when Institution User is the
selected role, clearing any stale selection when the role changes away from
it - preventing the confusing case of submitting a now-invalid combination
and hitting the new backend validation as a surprise.

**4. Password reset history was invisible in the Admin Panel.**
`GET /password-reset-requests` already returns up to 200 requests of every
status, but the UI discarded everything except PENDING before rendering,
so an administrator had no way to see what had already been approved or
rejected without opening the separate Audit Log. *Fix:* added a collapsed
"Recently decided requests" section immediately below the pending queue,
reusing the same already-fetched data - no new endpoint or request needed.

**Verified here:** the self-lockout logic via a standalone four-scenario
simulation (matching the reported symptom precisely, same discipline as
every prior fix); full backend compile clean; the full AST call-signature
cross-check (zero mismatches); brace/paren balance on the edited TSX file
(173/173, 190/190). `npm install` was attempted again in this fresh sandbox
session specifically to get a real `tsc` type-check - still blocked with the
same 403 Forbidden as the twenty-eighth item, so, as there, no
compiler-verified check of the frontend change was possible. **Not
executed:** all ten new/changed backend tests need the full FastAPI/
SQLAlchemy stack; rebuild and run `docker compose exec backend pytest -v`
to confirm. The frontend change should also be exercised directly: create a
user with each role (confirming the institution field's shown/required
behaviour), attempt to deactivate one's own admin account and the last
active admin (both should be refused with the new message), and deactivate/
reactivate an institution from its new buttons.


## Thirtieth item — first real run of the admin-side fixes: 2 failures, both corrected

The user ran the suite after the twenty-ninth item's admin-side fixes: 178
passed, 2 skipped, 2 failed (182 collected, up from 171). Both failures were
new findings - one a flawed test (not application code), one a genuine
regression the new validation introduced in an existing, unrelated test.

**Test defect: `test_admin_cannot_deactivate_the_last_other_active_admin`
expected a scenario that is logically unreachable.** With exactly two admins
(admin1, admin2), admin1 deactivating admin2 leaves admin1 - the caller -
still active, which is not a lockout at all; the test wrongly expected this
to be refused (400) and got 200. Proven with a standalone simulation before
touching any code: whoever is authenticated enough to reach
`deactivate_user()` is themselves necessarily active (a deactivated account
is rejected by the per-request authentication check before any endpoint
body runs), and self-deactivation is already blocked separately - so the
caller always satisfies their own "at least one other active admin" count,
making the twenty-ninth item's additional "other_active_admins == 0" branch
provably unreachable through the API. *Fix:* removed that branch from
`deactivate_user()` as dead code rather than leaving it to defend a state
the API cannot produce; self-deactivation blocking alone is both necessary
and sufficient. `test_admin_self_lockout.py` rewritten: the incorrect test
replaced with one confirming the caller remains active and administratively
capable afterward (and still cannot deactivate themselves even as the sole
remaining active admin) - four tests total, down from five.

**Regression: the twenty-ninth item's new role/institution validation broke
`test_strong_password_accepted_on_user_creation`, an existing, unrelated
test.** That test (and its neighbour, `test_weak_password_rejected_on_user_
creation`) created an INSTITUTION_USER without an `institution_id`, which
predates the new rule requiring one. Worse, on inspection,
`test_weak_password_rejected_on_user_creation` was found to still be
passing for the WRONG reason even before this run: the role/institution
check runs before the password-strength check in `create_user()`, so that
test's 400 could equally have come from the missing institution as from the
weak password, and only checked the status code, not why - a genuine gap
that would have silently kept "passing" even if password-strength
enforcement were removed entirely. *Fix:* both tests now supply a real
institution, and the weak-password test additionally asserts the word
"password" appears in the rejection detail, so it can only pass for the
reason it claims to test.

**Verified here:** the simplified self-deactivation-only logic via a
four-scenario simulation (self; only other admin, twice - once safe, once
blocked; a non-admin role); full backend compile clean. **Not executed:**
run `docker compose exec backend pytest -v` again to confirm 182 collected,
0 failed.


## Thirty-first item — Users table gave no visual sign a user is blocked by their institution's status

Found through direct use, not inspection: the user deactivated an
institution (Bank B) and then asked why its users still showed "Active" in
the Users table. This is expected, documented behaviour (KG-02,
account_status.py: `user.is_active` and `institution.is_active` are two
separate flags, and login checks both) - but the Users table only ever
displayed the user's own flag, giving no visible sign that the person is
in fact unable to log in right now because of their institution, not
themselves. Genuinely confusing for an administrator scanning the table.

**Fix.** The Users table now cross-references each row's `institution_id`
against the already-loaded institutions list; a user whose own account is
active but whose institution is not gets a "⚠️ Institution Deactivated"
badge next to their status, with a title tooltip explaining why. Computed
client-side from data the page already has - no new endpoint or request.

**Related improvement, same review:** the institution-deactivation confirm
prompt previously said "every user...will be unable to log in" without a
number. It now counts the institution's own currently-active users
(`users.filter(u => u.institution_id === i.id && u.is_active).length`) and
states the real figure, or says plainly that no active users exist yet if
none do - so an administrator sees the actual scale of the action before
confirming it, not a generic warning.

**Verified here:** brace/paren balance on the edited file (184/184,
204/204); the conditional logic traced by hand for all four combinations
(user active/inactive x institution active/inactive) to confirm the badge
shows only in the one case that matters (user active, institution not).
`npm install` was attempted again in this session specifically to get a
real `tsc` type-check - still 403 Forbidden, so, as with every frontend
change since the twenty-eighth item, no compiler-verified check was
possible. **Not executed:** rebuild and confirm visually - deactivate an
institution with active users, confirm the prompt states the correct
count, and confirm the badge appears on exactly those users (and disappears
on reactivation).


## Thirty-first item — Users table gave no visual indication of institution-level blocking

Found directly by the user while testing: deactivating Bank B's institution
correctly blocks every Bank B user from logging in (confirmed, item 29's
KG-02 enforcement), but the Users table in AdminPanel.tsx only ever reads
each user's OWN `is_active` flag - it kept showing "Active" for every Bank B
user, with nothing indicating they were now unable to sign in at all. This
was flagged as a known display gap during the admin-side review (item 29)
before the user encountered it directly.

*Fix:* the Users table now cross-references each user's `institution_id`
against the already-fetched `institutions` list (no new API call - both
were already loaded by `loadAll()`) and, for any user whose own account is
still active but whose institution is not, shows an amber "⚠️ Institution
Deactivated" badge next to their status with a tooltip explaining the
account itself is fine but currently blocked. Purely a display change - no
backend or authentication logic touched, since that logic (`account_status.
py`) was already correct.

**Verified here:** exact-occurrence counts on every new identifier
(`inactiveInstitutionIds`, `blockedByInstitution`, the badge text) confirmed
no accidental duplication; the `badge-medium` CSS class referenced already
exists; brace/paren balance on the full file (184/184, 204/204); backend
compile unaffected (this was a frontend-only change). **Not executed:** no
TypeScript compiler available in this sandbox (npm registry access is
blocked here, as in every prior frontend change this session) - rebuild the
frontend and confirm directly: deactivate an institution, confirm its
users show the new badge while individually deactivating one of them
(separately) still shows the plain "Deactivated" status without the badge.


## Thirty-second item — large TZS figures on the KPI cards were visually clipped

Found directly by the user: the Loan Value and Collateral Value KPI cards
could read as far smaller than their real value - "laki kadhaa" (a few
hundred thousand) when the true figure was in the billions. `formatTZS()`
itself was never the problem (confirmed: it always produces the full,
correctly comma-grouped number, e.g. "463,439,000,000 TZS" - nothing
abbreviated or rounded). The defect was purely visual: `.kpi-card-v2-text`
had `overflow: hidden`, and `.kpi-number` had `white-space: nowrap` with no
`text-overflow` indicator at all - so on a card as narrow as the grid's own
220px minimum, a 20-character figure at 1.32rem bold simply had its
right-hand digits sliced off with no ellipsis or any other sign that
anything was missing, reading as a plausible but wrong, much smaller number.

*Fix, CSS only (`index.css`):* `overflow: hidden` replaced with `min-width:
0` on the text container (the standard flexbox fix needed for a child to
actually shrink/wrap instead of overflowing its row); `.kpi-number` changed
from `white-space: nowrap` to `white-space: normal` with `overflow-wrap:
break-word` so a figure that cannot fit on one line wraps onto a second
instead of being clipped; font-size changed from a fixed 1.32rem to
`clamp(0.92rem, 1.6vw + 0.55rem, 1.32rem)` so it scales down gracefully on
narrower cards rather than forcing an even wider clipped line. No JSX,
`formatTZS()`, or backend logic touched - the underlying number was always
correct; only how it was allowed to display has changed.

**Verified here:** exactly one `.kpi-number` rule exists project-wide (no
conflicting override elsewhere to fight the fix); no media query touches
these classes; full CSS file brace balance (256/256); backend compile
unaffected (confirmed this is a CSS-only change). **Not executed:** no
browser available in this sandbox to render and visually confirm the wrap/
shrink behaviour at the grid's actual minimum card width - rebuild the
frontend and check the KPI cards directly, including at a narrow browser
width, to confirm the full figure is now always visible (wrapped or
shrunk, never cut off).


## Thirty-third item — KPI figures restored to original single-line look, sliding only when needed

Following the thirty-second item's fix (wrap-and-shrink), the user asked for
the ORIGINAL single-line, fixed-size, bold appearance to be kept exactly as
it was, but for any figure too wide for its card to still be fully readable
via a sliding ("slide") reveal rather than wrapping to a second line or
shrinking its font.

*Implementation:* `index.css`'s `.kpi-number` reverted to the original
fixed 1.32rem/`white-space: nowrap` single-line style. A new
`SlidingKpiNumber` component (`InternalPortal.tsx`) wraps the Loan Value and
Collateral Value figures specifically (the two that can legitimately run to
15-20 characters; Reporting Institutions and Total Submissions are always
short and were left as plain spans, unaffected). On mount and on window
resize, it measures the number's real rendered width (`scrollWidth`)
against its card's visible width (`clientWidth`); if and only if the number
is wider than the space available, it adds an `is-overflowing` class and
sets a CSS custom property (`--kpi-slide-distance`) to exactly the
overflow amount. A new `@keyframes kpi-slide` rule (pause → slide left by
that exact distance → pause → slide back), applied only via that class,
does the rest - a figure that already fits never animates or changes
appearance at all. `prefers-reduced-motion: reduce` disables the animation
for users who have asked their system not to show motion.

**Verified here:** brace/paren balance on both edited files
(`InternalPortal.tsx` 544/544 braces, 537/537 parens; `index.css` 264/264
braces, 255/255 parens); the `React` namespace is not imported anywhere in
this project (`"jsx": "react-jsx"` in tsconfig.json), so the type annotation
was written as a named `CSSProperties` import rather than `React.
CSSProperties`, which would not have compiled; backend compile unaffected
(frontend-only change). **Not executed:** no browser available in this
sandbox to actually render and watch the slide animation - rebuild the
frontend and confirm directly: a large loan/collateral figure should look
identical to before at rest, then smoothly reveal its hidden end and
return, on a loop, while the two short KPI cards next to it stay
completely static as before.


## Thirty-fourth item — brand colour changed from navy to charcoal green across navigation and headings

On request: replace the navy used in navigation and heading areas with
charcoal green (#2B353A).

`index.css`'s `:root` already centralised this exact tone as three
variables (`--color-primary`, `--color-primary-dark`, `--color-primary-
light`) plus `--color-heading`, documented in their own comment as "30%
deep navy (sidebar/headers/nav/primary text)" - confirmed by checking every
usage site before changing anything: the sidebar gradient, both portal
themes' `.portal-topbar` (the top navigation bar), and headings/labels
throughout all read these variables rather than a hardcoded value (39
usages total). Changing the four variable values alone re-themes the
sidebar, both topbars, and every heading that uses them, with no other
file touched.

`--color-primary` → `#2B353A` (as given); `--color-primary-dark` →
`#1C2326` and `--color-primary-light` → `#3E4D54`, computed as
proportional darker/lighter scalings of the same base (0.66x / 1.45x),
matching how the previous navy's own dark/light variants related to it -
preserving the same gradient and hover contrast relationships, just in the
new hue; `--color-heading` set to match `--color-primary`.

**Found and deliberately left unchanged, two hardcoded navy hex values that
bypass the variable system:** `HazardMap.tsx`'s highlighted-region map
label colour, and `InternalPortal.tsx`'s "Approved" segment colour in a
status chart. Both are data-visualisation colour choices, not navigation
or heading chrome, and the request was specifically scoped to navigation
and headings - changing a chart/map data colour without being asked could
misrepresent what that colour means elsewhere. Also left unchanged: the
Login page's decorative background gradient, which mixes the old navy
shades with gold for a hero visual effect rather than being a nav or
heading element. All three are flagged to the user as a follow-up option
for full brand consistency, not applied unilaterally.

**Verified here:** every one of the 39 variable usages found by search
before changing the values (not assumed); CSS brace balance after the edit
(264/264); no navy hex remains in the `:root` block; backend compile
unaffected (CSS-only change). **Not executed:** no browser available in
this sandbox to render the new theme - rebuild the frontend and confirm
the sidebar, both portal top bars, and headings now show charcoal green,
with the map label, chart segment, and login background colours unchanged
as intended.


## Thirty-fifth item — header redesigned to a two-tier gold-gradient / dark-navbar layout

On request, from a supplied design spec with exact colours and an HTML/CSS
reference: replace the single-bar topbar with a two-tier header - Tier 1 a
gold gradient (cream \u2192 gold \u2192 cream, #EFECE1/#D4B843) with Coat of Arms
(left), "Climate Data Repository" title (center), BOT emblem (right), and a
3px dark-gold (#9E7B1A) bottom border; Tier 2 a dark charcoal (#1E1E1E) bar
with a hamburger menu (left) and the signed-in user's role (right).

**Implemented in `PortalShell.tsx` + `index.css`**, replacing the old
single `.portal-topbar` and the sidebar's own internal brand-logo/toggle
(confirmed unused anywhere else first - `grep` across every `.tsx` file
found no other reference to either before removing their CSS). Four
deliberate decisions made explicit rather than silently assumed:

1. **No Tanzania Coat of Arms image file exists in this project** (only
   `bot_logo.png`, used for the BOT emblem side). A labelled placeholder
   (\U0001F1F9\U0001F1FF with a tooltip) occupies the correct position and
   layout slot - swap it for an `<img>` once the real file is supplied.
2. **The hamburger icon is wired to the sidebar's existing collapse/expand
   state** (the same toggle that used to live inside the sidebar itself),
   rather than being decorative, since the real navigation menu (Dashboard,
   Submissions, etc.) already lives in that sidebar.
3. **The role text is dynamic, not the literal hardcoded "BOT Analyst
   (internal)" from the spec** - `PortalShell` is shared by all three
   portals (Institution, BOT, Admin), so it shows "Institution User" /
   "BOT Analyst (internal)" / "System Admin" depending on who is actually
   signed in; hardcoding the BOT-specific label would have been wrong for
   the other two.
4. **The per-page title/subtitle and the notification bell - both already
   part of this shell before this redesign and absent from the supplied
   spec - were kept, not silently dropped**: placed in Tier 2 (title next
   to the hamburger, bell just before the role text) rather than removed,
   so no previously-working feature disappeared as a side effect of a
   visual redesign.

Theme-specific CSS overrides that referenced the now-removed selectors
(`.theme-institution .sidebar-toggle`, `.theme-bot .portal-topbar`, and
similar for both themes) were removed as dead code in the same pass; the
sidebar's own gradient, item states, footer, and accent-button theming
were left untouched. Both tiers use the exact literal colours from the
supplied spec, not theme variables - the design brief did not vary them by
role, so neither tier changes between the Institution and BOT themes.

**Verified here:** every one of the old classes being removed was
confirmed unused elsewhere by project-wide search before deleting its CSS;
brace/paren balance on both edited files (`PortalShell.tsx` 45/45 braces,
30/30 parens; `index.css` 254/254 braces); no duplicate class definitions
introduced (checked each new class's occurrence count individually).
**Not executed:** no browser available in this sandbox to render the new
header - rebuild the frontend and confirm directly: the two-tier layout,
the hamburger actually collapsing/expanding the sidebar, the role text
matching whichever account is signed in, and the notification bell still
working from its new position.


## Thirty-sixth item — real Tanzania Coat of Arms added, replacing the thirty-fifth item's placeholder

The user supplied the official Coat of Arms (uploaded image, matching
https://commons.wikimedia.org/wiki/File:Coat_of_arms_of_Tanzania.svg -
fetching that URL directly was attempted first and failed: both
commons.wikimedia.org and en.wikipedia.org are cache-only domains not
fetchable in this sandbox, and the raw upload.wikimedia.org file path is
not discoverable through text search since it is binary content, so a
computed MD5-hash-based guess at the path was rejected by the fetch tool's
own "must have appeared in a prior search result" rule).

**Legal note surfaced before implementing, and left in the code as a
comment for future maintainers:** Tanzania's National Emblems Act (Cap. 10)
restricts use of the Coat of Arms - unauthorised use "in connection with
business, trade" or by an individual without the Home Affairs Minister's
permission is an offence. This system's use (an internal Bank of Tanzania
system, a government body) is squarely the kind of official use the Act is
not aimed at restricting, but this is stated as a fact found, not legal
advice - BOT's own compliance process should confirm this, particularly
before any public-facing deployment.

**Implementation:** the uploaded file (a detailed illustration with a
plain white background, including white elements - e.g. the shield's wave
pattern - within the artwork itself) was copied to `tanzania_coat_of_arms.
jpg`. Naive colour-key transparency removal was deliberately not attempted,
since it would risk punching out those white details inside the emblem,
not just its background. Instead, `PortalShell.tsx`'s placeholder `<div>`
was replaced with an `<img>`, and `.coat-of-arms-placeholder` in `index.
css` replaced with `.coat-of-arms-badge` - a round white "medallion"
treatment (border-radius 50%, white background, drop shadow) that makes
the image's own white background look like a deliberate badge against the
gold gradient rather than an unstyled rectangle.

**Verified here:** the image's actual corner pixels confirmed pure white
(255,255,255) via PIL before deciding against colour-keying; Vite's bundled
`vite/client` ambient types (confirmed present in `vite-env.d.ts`) cover
`.jpg` imports the same way `.png` already worked for `bot_logo.png`, so no
new type declaration was needed; brace/paren balance on both edited files
(`PortalShell.tsx` 46/46 braces, 34/34 parens; `index.css` 255/255 braces,
253/253 parens). **Not executed:** no browser available in this sandbox to
render the result - rebuild the frontend and confirm the badge looks
correct against the gradient at actual size.


## Thirty-seventh item — hamburger menu changed to an off-canvas overlay, matching bot.go.tz

On request, modelled directly on the real site: `https://www.bot.go.tz/`
was fetched and its menu pattern confirmed - the navigation is hidden by
default (not a persistent sidebar) and the hamburger ("menu") slides it in
as an overlay on top of the page, with a visible "x" close control and
presumably a backdrop, rather than the collapse-to-icons behaviour this
project had implemented instead (thirty-fifth item).

**Implementation (`PortalShell.tsx` + `index.css`):** the sidebar's
`collapsed` boolean (default open, narrows to icons) was replaced with
`menuOpen` (default CLOSED, fully hidden). `.portal-sidebar` changed from a
normal flex column that reserved layout width to `position: fixed`,
translated fully off-screen (`translateX(-100%)`) and sliding into view
(`.open { translateX(0) }`) over the content on a 0.28s transition - it no
longer takes up any space when closed, so `.portal-main` no longer needs
`flex: 1` against it (cleaned up to a plain `display:flex` column). A new
`.sidebar-backdrop` (dark, semi-transparent, `z-index: 1000`, below the
sidebar's `1001` - confirmed higher than every other z-index in the
project first) appears only while open and closes the menu on click,
matching the real site. A close "×" button now sits inside the sidebar
itself, and choosing any navigation item (including Change Password/Log
Out) closes the menu afterward (`handleNavItemClick`), rather than leaving
it open over whatever page it navigated to.

The icon-only "collapsed" rendering (hiding labels, hiding the platform
list) no longer applies, since the sidebar is now always shown at full
width when open and fully hidden otherwise - there is no narrow
intermediate state in the requested pattern, so that conditional rendering
was simplified away along with it.

**Verified here:** the live bot.go.tz page was fetched directly to confirm
the slide-in/backdrop/close-button pattern before implementing it, not
assumed from the name "hamburger" alone; every other z-index in the
project checked and confirmed lower than the new overlay's; brace/paren
balance on both edited files (`PortalShell.tsx` 46/46 braces, components
after edit; `index.css` 259/259 braces); a `.sidebar.collapsed` /
`--sidebar-w-collapsed` pair found in `index.css` during this pass is
unrelated pre-existing dead code (a different, unprefixed `.sidebar` class
never referenced by any `.tsx` file, confirmed by search) and was left
alone, consistent with how the thirty-fifth item treated similar
pre-existing dead CSS. **Not executed:** no browser available in this
sandbox to render or click through the result - rebuild the frontend and
confirm directly: the menu is hidden on load, the hamburger slides it in
over a dark backdrop, the "×" and backdrop both close it, and selecting a
navigation item both navigates and closes the menu.


## Thirty-eighth item — gold accent colour unified with the header, BOT logo added to the sidebar

Two requests: (1) every button/accent already using the project's gold
colour should match the exact gold used in the top-header gradient, not
the older, separate gold the rest of the app had; (2) the BOT logo should
also appear above the navigation items in the (now off-canvas) sidebar.

**Gold unification:** `--color-gold`/`--color-gold-dark`/`--color-gold-
light` - the three variables already driving all 34 existing gold usages
project-wide (buttons, active sidebar items, login-page accents, etc.) -
were changed from the older `#D4AF37`/`#B89228`/`#E4C468` to `#D4B843`/
`#9E7B1A` (the header's own metallic-gold and dark-gold-border colours,
used verbatim) and a newly computed `#FEDD50` for the light variant (1.2x
scaling of the base, the same proportional method used for the charcoal-
green dark/light variants in the thirty-fourth item - needed because the
header's own third colour, the pale cream edge #EFECE1, is too washed-out
to serve as a contrast accent, e.g. an active sidebar item's left border,
which is what `--color-gold-light` is actually used for). Confirmed first,
no `.tsx` file hardcodes any of the old gold hex values outside this
variable system, so updating the three values alone re-themes every usage
with no other file touched.

**BOT logo in the sidebar:** `PortalShell.tsx`'s `.sidebar-close-row` (so
far just the "×" close button, right-aligned) now also shows the BOT
logo on the left, with `justify-content` changed from `flex-end` to
`space-between` to place them at opposite ends - the same `botLogo` import
already in the file for the header's own BOT emblem, not a new asset.

**Verified here:** every existing usage of the three gold variables found
by search before changing their values (34 total, confirmed none
hardcoded elsewhere); brace/paren balance on both edited files
(`PortalShell.tsx` 47/47 braces, 49/49 parens; `index.css` 260/260 braces,
265/265 parens); backend compile unaffected (frontend-only change). **Not
executed:** no browser available in this sandbox to render the result -
rebuild the frontend and confirm directly: every gold-accented
button/active-state now matches the header's own gold, and the BOT logo
appears at the top of the sidebar when the off-canvas menu is opened,
beside the close button.


## Thirty-ninth item — sidebar logo centered, sidebar background lightened, top-header title/logo adjusted

Three requests. (1) Center the BOT logo added to the sidebar header row in
the thirty-eighth item (it had been left-aligned, sharing the row with the
close button via space-between). (2) Change the sidebar's own background to
match "the project's overall background... used in the pie chart's None
slice" - two distinct colours were found (`--color-bg: #F8F9FA`, the
project's actual background variable, versus `HAZARD_NONE_COLOR:
#B8B4A8`, the pie chart's muted grey-beige "no hazard" slice) and
`--color-bg` was used as the precise match for "the project's overall
background", since that is literally what the variable is for and is
consistent with the "a certain white" description; flagged to the user in
case the pie-chart grey was the one actually meant. (3) In the top-header:
change the title text to "Bank of Tanzania" (rendered as "BANK OF
TANZANIA" - the existing `text-transform: uppercase` on `.top-header-title`
handles the capitalisation, so the JSX source stays normal-case for
semantic/accessibility reasons rather than literal screaming-caps), and
enlarge the BOT emblem so it carries similar visual weight to the Coat of
Arms beside it.

**Sidebar background change required also flipping its text/hover/border
colours**, not just the background - the sidebar's text, item colours and
hover states were all authored for a DARK background (white/near-white at
various opacities) from when it had the navy gradient; switching only the
background to a light colour without this would have made the sidebar
unreadable. For both `.theme-institution` and `.theme-bot`:
`.portal-sidebar`'s text colour changed to `var(--color-text)` with a
`var(--color-border)` right edge (the gradient and sidebar-specific
`color: rgba(255,255,255,0.92)` removed); `.sidebar-item`'s colour to
`var(--color-text)`; its `:hover` background/text from pale-white-on-dark
to a subtle dark tint (`rgba(0,0,0,0.045)`) with `var(--color-heading)`
text. `.sidebar-item.active` (gold background) was left as-is - white text
on the gold accent still has good contrast regardless of the surrounding
background. Checked and confirmed unaffected, since they inherit the
parent's now-dark text colour automatically rather than hardcoding white:
`.sidebar-section-label`, `.sidebar-platform-list`/`.platform-row`. Left
deliberately untouched: `.theme-bot .bell-trigger`/`.bell-badge` (the
notification bell lives in the separate, still-dark `.navbar`, not the
sidebar) and `.portal-footer` (the user said "navigation bar", not footer).

**Logo centering:** `.sidebar-close-row` changed from `justify-content:
space-between` to `center` with `position: relative`; `.sidebar-close`
itself now `position: absolute` in the row's top-right corner, so the logo
centers independent of the close button sitting on top of it.

**Verified here:** every sidebar-text-dependent selector checked
individually for hardcoded white before deciding none needed a separate
fix (confirmed via direct inspection, not assumption); brace/paren balance
on both edited files (`PortalShell.tsx` 47/47 braces, 49/49 parens;
`index.css` 261/261 braces, 267/267 parens); backend compile unaffected.
**Not executed:** no browser available in this sandbox - rebuild the
frontend and confirm directly: the sidebar is now light with dark,
legible text in both themes, the BOT logo sits centered above the nav
items, and the top header reads "BANK OF TANZANIA" with a visibly larger
BOT emblem.


## Fortieth item — language switching (EN/SW), Stage 1: shared chrome and Login

On request: a working language-switch button. Given the scale found before
starting (3,084 lines across the frontend, InternalPortal.tsx alone 1,193)
and that this sandbox cannot `npm install` a library like react-i18next
(confirmed blocked again, same as every prior frontend-dependency attempt
this session), a staged plan was proposed and agreed: build the switching
infrastructure plus translate the chrome shared by every page (PortalShell)
and the Login page first; each portal's own page content (InternalPortal,
InstitutionPortal, AdminPanel) is deliberately left for separate, later
requests rather than attempted in one large, error-prone pass.

**Implementation, entirely dependency-free:** `i18n/translations.ts` (a
plain `{en: {...}, sw: {...}}` dictionary, 29 keys) and `context/
LanguageContext.tsx` (a `LanguageProvider` + `useLanguage()` hook, built to
match this project's existing `AuthContext.tsx` pattern exactly) persist
the chosen language to `localStorage` the same way `AuthContext` already
persists the session. `main.tsx` wraps the app in `LanguageProvider`
alongside the existing `AuthProvider`. A pill-shaped toggle button (🌐 EN /
🌐 SW) was added to `PortalShell.tsx`'s navbar (next to the notification
bell) and, separately, to `Login.tsx` (top-right corner, since that page
has no navbar) - clicking it calls `toggleLanguage()`, which flips the
stored language and re-renders every `t('key')` call immediately.

Every hardcoded string in `PortalShell.tsx` (navigation section label,
Change Password/Log Out, Integrated Platforms, Connected/Not Connected,
the three role labels, the header title, the footer support line, both
hamburger/close aria-labels) and `Login.tsx` (title, subtitle, both field
labels, forgot-password link, submit button state, the authorized-access
notice, the demo-accounts block and its synthetic-data warning, the
copyright line) was replaced with a `t('...')` call. `SidebarItem.label`
(the page-specific nav item text like "Dashboard", "Submissions") is
supplied by each *calling* page, not by `PortalShell` itself, so those
labels remain English for now - in scope for the later per-page stages,
not silently translated halfway.

**Verified here:** every `t('...')` call across both edited files
cross-checked programmatically against the dictionary - 29 keys used, 29
defined in each language, zero missing in either direction, zero defined-
but-unused ("dead") keys; brace/paren balance on every new or edited file
(`Login.tsx` 44/44 braces; `PortalShell.tsx` 62/62; `LanguageContext.tsx`
15/15; `translations.ts` 3/3; `main.tsx` 3/3; `index.css` 264/264); backend
compile unaffected. **Not executed:** no browser available in this sandbox
to click the toggle and watch the UI actually re-render in Swahili -
rebuild the frontend and confirm directly, on both the Login page and
after signing in: the button switches language immediately, the choice
survives a page reload (localStorage), and every translated string reads
correctly in both languages.


## Forty-first item — language switching (fortieth item) reverted on request

The user decided against the language feature before extracting/wiring the
new files into their own working copy, and asked for it removed.

Fully reverted: deleted `frontend/src/i18n/` (the translation dictionary)
and `frontend/src/context/LanguageContext.tsx`; `main.tsx` back to wrapping
the app in `AuthProvider` alone (no `LanguageProvider`); `PortalShell.tsx`
and `Login.tsx` back to their hardcoded English strings with every
`useLanguage`/`t('...')` call and the language-toggle buttons removed;
`index.css`'s `.language-toggle` and `.login-language-toggle` rules
removed.

**Verified here:** project-wide search confirms zero remaining references
to `useLanguage`, `LanguageContext`, `LanguageProvider`, `i18n/
translations`, or `language-toggle` anywhere; brace/paren balance on every
touched file, and - specifically checked rather than merely balanced -
`PortalShell.tsx` (47/47 braces, 49/49 parens) and `index.css` (261/261
braces, 267/267 parens) match the exact counts recorded at the end of the
thirty-ninth item (the last verified state before the language feature was
added), confirming this is a complete, clean revert rather than a
same-shape-different-content rewrite; backend compile unaffected
(frontend-only). **Not executed:** no browser available in this sandbox -
rebuild the frontend and confirm the app behaves exactly as it did before
the fortieth item, with no language toggle visible anywhere and no
build/runtime errors from the removed imports.


## Forty-second item — BOT logo sized to exactly match the Coat of Arms

The title ("Bank of Tanzania", already rendered as "BANK OF TANZANIA" via
the existing `text-transform: uppercase` on `.top-header-title` since the
thirty-ninth item) needed no change. The BOT logo, at 52px since the
thirty-ninth item (deliberately slightly larger than the Coat of Arms
badge's 48px, to compensate for perceived visual weight), was changed to
exactly 48px on request - an exact match rather than a close one.

**Verified here:** both `.coat-of-arms-badge` and `.top-header-bot-logo`
confirmed at identical `width: 48px; height: 48px;` by direct inspection
after the edit; CSS brace balance (261/261); backend compile unaffected
(CSS-only change). **Not executed:** no browser available in this sandbox
- rebuild the frontend and confirm the two emblems read as the same size
on either side of the title.


## Forty-third item — header rebuilt to a proportion-driven two-strip spec

A detailed spec replaced the earlier header: a gold banner over a dark
strip with fixed proportions, an unframed Coat of Arms, a square BOT
emblem, and a hamburger-only dark strip. This supersedes the thirty-fifth,
thirty-sixth, thirty-ninth and forty-second items' header details (round
medallion badge, 48px emblems, #1E1E1E strip, #D4B843 gradient).

**Proportions are formula-driven, not hard-coded.** `--header-top-h:
clamp(80px, 9vw, 112px)`; the bottom strip is `0.65 x` it, both emblems
`0.85 x` it. Computed at eight widths (360-1920px): bottom/top = 0.65 and
logo/top = 0.85 at every one. Width:height is 11.1:1 at 1000-1244px; above
that the 112px cap makes it 12-17:1 (12.9:1 at 1440px). The spec's "roughly
11:1" and "compact" conflict on large screens (strict 11:1 would be 131px at
1440px and 175px at 1920px, before the dark strip), so the cap is a judgment
call - raise the 112px in the clamp to taste.

**Colours per spec:** gradient #F5F3ED -> #E1C352 -> #F5F3ED; divider 3px
#9E7B27; title #0B2540; dark strip #1A1A1A. The project-wide accent gold
variables (--color-gold etc., from the thirty-eighth item) were NOT changed
and remain #D4B843-based, so buttons are now slightly different from the
header's gold; flagged rather than changed unasked.

**Assets.** (1) *Coat of Arms*: the supplied JPG had a white background, and
the spec forbids the round frame that had hidden it. Background removed by a
flood fill from the image border (only white connected to the edge becomes
transparent, so white inside the artwork survives), plus removal of the four
large enclosed gaps between the tusks and shield, told apart from the ivory
tusks by position because their colour is identical (~253,253,253). Checked
on gold, cream and black: tusks, shield waves and the UHURU NA UMOJA ribbon
intact. Saved as tanzania_coat_of_arms.png; the JPG was deleted. (2) *BOT
emblem*: bot_logo.png is 235x115 but its artwork is only 123x98 inside
transparent margins, which is why it always looked small in square boxes
(~25px of artwork in a 48px box). Trimmed and padded to an exact square as
bot_logo_square.png, used only in the header; the original stays for the
sidebar and login. Its colour (mean RGB 228,170,84) is already gold/amber,
so it was not recoloured. The spec's "1:0.85" was read as height:width,
which matches the artwork's natural ~1:0.86, so the aspect is preserved.

**Structure.** `.top-header` is a 3-column grid (`1fr auto 1fr`) so the
title is centred exactly although the two emblems differ in width. The
hamburger is a 24x24 SVG in a 1px white dotted box; both strips share
`--header-pad-x`, aligning it with the Coat of Arms' left edge.

**Removed from the dark strip, relocated rather than deleted.** The spec
leaves the strip's right side empty and its left as the hamburger only, but
the page title/subtitle, the notification bell and the role label were
working features. They moved to a `.page-header-row` at the top of the
content area. The bell's `.theme-bot` overrides (white on translucent, for
the dark strip) were removed since they would have made it invisible on the
light content background.

**Verified here:** the proportion maths at eight widths; the image
processing, visually on three backgrounds; a pixel-value mock of the header
at 1244px rendered with the real assets (the available wkhtmltoimage engine
cannot run CSS grid/clamp()/var(), so this checks the design, NOT the
stylesheet itself); brace/paren balance (`PortalShell.tsx` 47/47, 45/45;
`index.css` 258/258, 280/280); no frontend test references the changed
UI; backend compile unaffected. **Not executed:** the real CSS in a real
browser - rebuild and check the header at a few window widths, the
hamburger still opening the menu, and the bell opening from its new place.


## Forty-fourth item — header strip heights changed to the supplied exact pixel values

The project owner replaced the forty-third item's proportions (bottom strip
0.65x the top, sized by `clamp(80px, 9vw, 112px)`) with measurements of the
Bank of Tanzania site: at 1920px wide, banner 110px and nav strip 45px; at
375px wide, banner 80px and nav strip 50px, with a 768px breakpoint. These
numbers come from the owner and were not independently measured here.

**Implementation (`index.css`):** `--header-top-h` / `--header-bottom-h` are
now fixed - 110px / 45px, overridden to 80px / 50px inside
`@media (max-width: 768px)`. The emblems remain 0.85x the banner height
(carried over from the earlier spec; the new measurements do not mention
them), i.e. 93.5px desktop and 68px phone. A `@media (max-width: 480px)` rule
lets the title wrap instead of colliding with the emblems on very narrow
phones; at 375px it still fits on one line.

**The supplied CSS used `aspect-ratio` alongside an explicit width and
height; it was not copied.** With both dimensions set, `aspect-ratio` has no
effect, so it would only have implied a behaviour the code does not have.
The ratios are documented in a comment as what those fixed heights produce
at those widths. Between the two measured widths the heights do not scale -
they hold the nearest state's value (so a 1024px window gets the 110px
banner, a 9.3:1 shape).

**Verified here:** computed at 1920px and 375px, the CSS values reproduce
every supplied figure exactly, including the exact fractions (192/11,
128/3, 75/16, 15/2), the 2.44 : 1 and 1.6 : 1 strip ratios and the ~71%
banner share on desktop; the breakpoint was checked at 768px/769px; the
emblem-fit check shows the side columns hold the emblems at every width
from 360px up, and at 320px the title wraps (the <=480px rule) instead; two
pixel-value mocks (1920px and 375px) rendered with the real image assets.
As before, the available wkhtmltoimage engine cannot run CSS grid/var(), so
the mocks check the design, not the stylesheet itself. Brace/paren balance:
`index.css` 262/262, 280/280; `PortalShell.tsx` 47/47, 46/46; backend
compile unaffected. **Not executed:** the real stylesheet in a real browser
- rebuild and check the header at a desktop width and at phone width (the
browser's device toolbar at 375px is enough).


## Forty-fifth item — header emblems set to the supplied fixed sizes

The project owner supplied approximate emblem measurements from the Bank of
Tanzania site: desktop (1920px) Coat of Arms 85x100px (17:20) and BOT
emblem 95x95px (1:1); phone (375px) 50x60px (5:6) and 55x55px (1:1). These
replace the forty-fourth item's "0.85x the banner height" sizing (93.5px
desktop / 68px phone for both). The figures are approximate in the source
("~85px") and were used as exact; they were not independently measured here.

**Implementation (`index.css`):** `--header-logo-h` removed; new variables
`--header-coat-w`, `--header-coat-h`, `--header-bot-size` with a 768px
override, consumed by `.top-header-coat` (explicit width and height,
`object-fit: contain`) and `.top-header-bot-logo` (square box). As in the
forty-fourth item, the supplied CSS's `aspect-ratio` was not copied: it has
no effect when width and height are both set.

**Verified here (computed from the real image files):** the boxes equal the
supplied ratios (17/20, 5/6, 1:1); desktop the Coat of Arms is 1.05x taller
than the BOT emblem and the emblem 1.12x wider, as supplied. The Coat of
Arms artwork is 329x383 (0.859), so `contain` draws it 85x99px and 50x58px
- about 1% short of its box height, undistorted. (An earlier comment in the
stylesheet said ~0.862/~1.3%; corrected.) Both emblems fit inside the
banner's content height (107px desktop, 77px phone; the 3px border is
inside the banner), with margins of 3.5px (Coat of Arms) and 6px (BOT) on
desktop. Horizontal fit holds from 320px up with the title on one line; the
<=480px wrap rule only matters below that. Mocks at 1920px and 375px
rendered with the real assets - computed pixel values in wkhtmltoimage,
which cannot run CSS grid/var(), so they check the design, not the
stylesheet itself.

**Worth knowing:** the BOT file's artwork is wider than tall (123x98, ~1.26:1)
even though it is shown in a 1:1 box, so it fills the box's width and about
80% of its height - it will look a little smaller than a full-height square
logo. If the BOT site's own logo is a squarer artwork than the file we have,
supplying that file is the real fix; stretching this one would distort it.

Brace/paren balance: `index.css` 262/262, 285/285; `PortalShell.tsx` 47/47,
47/47; backend compile unaffected. **Not executed:** the real stylesheet in
a real browser - rebuild and check desktop and a 375px viewport.


## Forty-sixth item — top banner made slightly thinner

On request ("reduce the thickness of the top banner very slightly"), the
banner height went from 110px to 105px on desktop and from 80px to 76px at
<= 768px (about 4.5% and 5%). The dark strip (45px / 50px) and the emblem
sizes were deliberately left as supplied: the request named only the banner.
Consequences: banner : strip is now 2.33 : 1 on desktop (was 2.44) and 1.52 : 1
on phones (was 1.6); the banner is 18.29 : 1 at 1920px and 4.93 : 1 at 375px.

**There is a floor, and this is close to it.** The banner's content height is
its height minus the 3px bottom border (102px desktop, 73px phone) and the
Coat of Arms is 100px / 60px tall, so desktop cannot go below 103px without
also shrinking the Coat of Arms. At 105px it has 1px above and below; the BOT
emblem (95px) has 3.5px. Compared side by side in a mock at real pixel size,
110px versus 105px: nothing clipped, but the Coat of Arms now sits close to
the banner's top edge. Going thinner than this needs smaller emblems, which
the supplied sizes do not allow.

`--header-top-h` (105px, and 76px inside the 768px media query) is the single
value to change. The explanatory comment in `index.css` and the one in
`PortalShell.tsx` were updated to say the banner was trimmed from the measured
values, and to record the new ratios and the fit floor.

**Verified here:** the new ratios computed; the fit floor derived from the
actual emblem heights; a before/after mock with the real image assets (the
wkhtmltoimage engine cannot run CSS grid/var(), so this checks the look, not
the stylesheet itself); brace/paren balance (`index.css` 262/262, 288/288;
`PortalShell.tsx` 47/47, 47/47); backend compile unaffected. **Not executed:**
the real stylesheet in a real browser - rebuild and look at the Coat of Arms'
clearance at the banner's top and bottom edges.


## Forty-seventh item — page title, notification bell and role label returned to the dark strip

On request, the dark strip now shows the page title and subtitle immediately
after the hamburger and, on its right, the notification bell followed by the
role label. This supersedes the earlier hamburger-only / empty-right spec
and the interim arrangement (forty-third item) that had moved these three
things into a row at the top of the content area; that row and its CSS were
removed.

**What "Climate Data Repository" and its tagline are.** They are not
hard-coded in the shared header: they are the `pageTitle` / `pageSubtitle`
props, and only `InternalPortal.tsx` passes those exact words ("Climate Data
Repository" / "Reliable climate data. Informed decisions. Resilient financial
sector."). The other two portals pass their own - "System Administration" /
"Identity, access, and institution management" and "Overview" / "Your
institution's reporting dashboard" - so each portal shows its own title in the
strip. Changing the other two to say "Climate Data Repository" would be a
one-line edit per page, but was not done unasked.

**Layout (`index.css`, `PortalShell.tsx`):** `.navbar` is a flex row with
`justify-content: space-between`; `.navbar-left` holds the hamburger and the
two-line title block, `.navbar-right` the bell and role. `min-width: 0` on the
flex children plus `text-overflow: ellipsis` let the long tagline truncate
instead of pushing the bell and role off-screen. The bell's styling was
written for a light background, so `.navbar .bell-trigger/.bell-badge` now
give it the light-on-dark treatment - scoped to `.navbar` rather than to one
portal theme, since the strip is the same colour in every portal. (The
earlier `.theme-bot`-only overrides had been deleted in the forty-third item
when the bell moved onto the light content area.)

**Narrow screens.** Estimated at ~215px for the bell and role and ~190px for
the title, the role label cannot fit beside a readable title below roughly
520px, so it is hidden at `max-width: 560px` (an initial 480px threshold would
have started truncating the title at 481-520px). The bell and title stay; the
tagline truncates with an ellipsis. So at phone width the role label from the
request is NOT shown - flagged, not silent.

**Verified here:** the title, tagline, bell, badge and role arrangement in a
mock at 1366px and 375px using the real image assets (the available
wkhtmltoimage engine cannot run CSS grid/var(); the mock uses explicit
pixels and approximate text widths from a different font, so it checks the
arrangement, not the stylesheet); grep confirms no `page-header` leftovers;
brace/paren balance (`index.css` 268/268, 291/291; `PortalShell.tsx` 47/47,
48/48); backend compile unaffected. **Not executed:** the real stylesheet in
a real browser; also not tested: the notification panel opening from its
restored position (it is absolutely positioned under the bell with its own
background and text colour, so it should be unaffected, but this was
reasoned, not run).


## Forty-eighth item — banner, emblems and title each reduced by 10%

On request: "reduce the size of the top banner strip by 10%, the logos by 10%,
and the words BANK OF TANZANIA by 10%". Applied as x0.9 to each:

| | before | after |
|---|---|---|
| Banner height, desktop | 105px | 94.5px |
| Banner height, phone (<= 768px) | 76px | 68.4px |
| Coat of Arms, desktop / phone | 85x100 / 50x60px | 76.5x90 / 45x54px |
| BOT emblem, desktop / phone | 95 / 55px square | 85.5 / 49.5px square |
| Title font | clamp(1.05rem, 2.6vw, 2rem) | clamp(0.945rem, 2.34vw, 1.8rem) |

**Interpretation, stated rather than assumed.** The request says "ukubwa wa
ulalo wa strip" ("the size of the horizontal [aspect] of the strip"), which is
ambiguous. It was read as the strip's height/thickness, consistent with the
previous request about the banner's thickness; a full-width banner cannot be
made narrower without leaving gaps at its sides. The dark nav strip (45px /
50px) was not touched - the request named the top banner only.

**Resulting ratios** (the comment above `--header-top-h` in `index.css` was
rewritten, including the history of the two reductions): desktop 1920:94.5 =
20.32 : 1, banner : nav strip 2.10 : 1 (was 2.33); phone 375:68.4 = 5.48 : 1,
1.37 : 1 (was 1.52). The aspect ratios of the emblem boxes are unchanged
(0.850 and 0.833; BOT 1 : 1), and on desktop the Coat of Arms is still 1.05x
taller and the BOT emblem 1.12x wider than the other.

**Fit.** Banner content height is the height minus the 3px border: 91.5px
desktop, 65.4px phone. The Coat of Arms artwork is drawn at 76.5x89px
(desktop; 45x52px phone), leaving ~1.2px above and below it on desktop (was
~1.5px) and 6.5px on phones; the BOT emblem has 3px / 7.95px. The floor is
~93px (desktop) and ~57px (phone). Because the emblems scale with the banner,
this clearance stays about as tight as before; it is not worse, but it is not
roomy either.

**Verified here:** the arithmetic and clearances from the real image
dimensions; a before/after mock at 1366px and an after mock at 375px with the
real assets (the wkhtmltoimage engine cannot run CSS grid/var()/clamp(), so it
checks the look using explicit pixels, not the stylesheet itself); brace/paren
balance (`index.css` 268/268, 293/293; `PortalShell.tsx` 47/47, 47/47);
backend compile unaffected. **Not executed:** the real stylesheet in a real
browser.


## Forty-ninth item — Coat of Arms 10% shorter, BOT emblem paler, title less bold

Three requests: cut the Coat of Arms' height by 10%; make the BOT emblem's
very deep colour "a little pale gold"; reduce how bold "BANK OF TANZANIA" is.

**Provenance, stated plainly.** When this pass started, the working tree
already contained all three changes (a new `bot_logo_square_pale.png`, the
Coat of Arms at 68.85x81px, the title at weight 600) with comments written in
this project's usual style, but they were not in this session's visible step
history, so it cannot be said where they came from. The previously delivered
ZIP had none of them (title weight 800, original-colour emblem, Coat of Arms
76.5x90). Rather than redo or blindly trust them, each was audited against the
files; the results below are from that audit.

**1. Coat of Arms.** 90 -> 81px tall on desktop and 54 -> 48.6px on phones, with
the width following (76.5 -> 68.85px; 45 -> 40.5px) so the box stays 17:20
(5:6) and the artwork is not distorted or left floating off the hamburger's
left edge. Drawn artwork ~68.85x80px. Side effect: the Coat of Arms is now
shorter than the BOT emblem (85.5 : 81, i.e. the emblem is 1.06x taller and
1.24x wider; about equal in height on phones), the reverse of the original
measurements. The comment's fit floor was updated: the tallest emblem is now
the BOT one, so the banner needs >= 88.5px desktop / 52.5px phone, and the
Coat of Arms has ~5.7px clearance above and below (was ~1.2px).

**2. BOT emblem colour.** A new file, `bot_logo_square_pale.png`, is the
square emblem with each pixel's RGB moved 45% of the way toward #ECD696.
Audited: alpha channel identical to the original (max difference 0); the
colour change reproduces exactly as that blend (mean error 0.25/255); mean
colour #E4AA54 -> #E8BE72, matching the stylesheet comment. It was compared
visually against four independent CSS-filter candidates (saturate/brightness/
hue-rotate, computed with the filter-spec formulas): it is paler than all of
them. Cost: contrast against the banner's cream end (#F2EBD4 where the emblem
sits) falls from 1.94 to 1.56 (median emblem colour) and 2.66 to 1.85 (darker
pixels) - still visible in mocks, fainter than before, and decorative rather
than text. `bot_logo_square.png` is kept and unused, so reverting is a one-
import change in `PortalShell.tsx`; the sidebar and login page still use the
unmodified `bot_logo.png`. Making it slightly less pale means regenerating the
file at a smaller percentage.

**3. Title weight.** `font-weight: 800 -> 600` on `.top-header-title`.
`index.html` loads Inter from Google Fonts at weights 400-800, so 600
(SemiBold) is a real face when online; offline the stack falls back to the
system font (Segoe UI SemiBold on Windows). Letter-spacing and size unchanged.

**Verified here:** the asset audit above; syntax balance (`index.css` 268/268,
296/296; `PortalShell.tsx` 47/47, 48/48); a before/after mock at 1366px and an
after mock at 375px with the real assets; no stale numbers left in the header
comments (the one remaining mention of 85x100 is the history of the original
measurements); backend compile unaffected. **Not verifiable here:** the title's
weight change - the mock engine has one bold face only, so it cannot show 600
versus 800; and the real stylesheet in a real browser.


## Fiftieth item — new banner gradient, flag-coloured line, and the same gold gradient on every gold box

Supplied CSS: `.strip-background` (`linear-gradient(to right, #E8E3CE 0%,
#D9BD59 50%, #EAE8E3 100%)`) and `.strip-bottom-border` (`4px solid` with
`border-image: linear-gradient(to right, #1EB53A, #000000, #00A3E0) 1`, the
Tanzanian flag's green, black and blue), plus the instruction that every gold
box use that same gradient.

**Banner.** Both supplied classes were added and applied to the header element
together with `.top-header`, whose own `background` and `border-bottom` were
removed so nothing conflicts. The gradient lives once in `--gold-gradient`
(`:root`) and `.strip-background` uses it - identical to the supplied rule.
The line is 4px instead of 3px; because the banner has a fixed border-box
height, its content area is 1px shorter (90.5px desktop, 64.4px phone), leaving
the BOT emblem 2.5px above and below on desktop (7.45px on phones). Comments
in `index.css` and `PortalShell.tsx` that quoted the old gradient, colours and
3px line were updated.

**Gold boxes now using the gradient** (hover = the same stops darkened 10%,
`--gold-gradient-hover`): the generic `button` rule (every button without a
variant class, including a lone `btn-sm`), `button.btn-gold`, `.btn-accent`
(both portal themes), `.login-submit`, and the active sidebar item (both
themes). The variant buttons (`btn-secondary`, `btn-success`, `btn-danger`)
use the `background` shorthand, which discards the generic gradient entirely,
so they are unaffected; there is no `background-color` anywhere that could let
the gradient show through underneath.

**Deliberately NOT changed, because they are not boxes or they encode data:**
text and border colours that use the flat gold variables, focus rings, the
login card's top border, the notification dot (8px), the chart bar fills
(`.bar-viz-fill`, which encode amounts), the login page's blurred decorative
circles, and the map's highlighted-region label in `HazardMap.tsx` (map data
annotation). Unused leftovers from the old `.sidebar` class family
(`.sidebar-brand-icon`, `.badge-count`) also still use flat gold; nothing
renders them.

**Text colour had to change on two boxes.** The login button and the active
sidebar item had WHITE text on gold. On this gradient white measures 1.29 /
1.85 / 1.22 : 1 (left edge / centre / right edge), i.e. unreadable at the pale
ends, so their text is now `--color-primary-dark` (12.4 / 8.6 / 13.0 : 1). The
default button text (`--color-primary`, 9.8 / 6.8 / 10.3 : 1) was already dark.

**One incidental fix.** `.link-button` ("Mark all as read") had no hover of its
own, so it inherited `button:hover`: previously a gold-dark background behind
gold-dark text (the label disappeared on hover - an existing bug), and it would
have become a gradient chip behind a small text link. It now has
`.link-button:hover { background: none; text-decoration: underline; }`. Every
other button class in the TSX files was checked for its own hover rule.

**Consequences worth knowing.** (1) The gradient is pale at both ends, so a gold
button's left and right edges are close to the page background (#FBFAF6): the
shape is defined mostly by its darker centre and, on the login button, its
shadow. The active sidebar item likewise fades toward the sidebar's near-white
background on its right. A thin border would define them; not added unasked.
(2) The new gradient's right end (#EAE8E3) is slightly darker than the old one
(#F5F3ED), so the pale BOT emblem (forty-ninth item) now has ~1.46 : 1 contrast
against the banner behind it (median emblem colour; 1.56 on the old gradient;
1.94 before the emblem was paled). (3) `button`'s `transition: background`
cannot animate a gradient, so the hover change is instant.

**Verified here:** the contrast figures computed from the actual colours;
every remaining flat-gold background listed and accounted for; a button-class
inventory against their hover/background rules; brace/paren balance
(`index.css` 271/271, 302/302; `PortalShell.tsx` 47/47, 49/49); backend compile
unaffected; a mock at 1366px of the banner, line, buttons, login button and
active item. **Not verifiable here:** the flag-coloured line as a real
`border-image` - the mock engine does not support it, so the line in the mock
is a separate 4px gradient strip standing in for it; and the real stylesheet in
a real browser.


## Fifty-first item — gradient line under every item in the navigation list

Request: apply a supplied snippet (`.kipengele-cha-dashboard`: a 4px
transparent bottom border with `border-image: linear-gradient(to right,
#00A3E0, #33CCFF) 1`) to every item in the navigation list.

**What "every item" is.** The three kinds of button in the sidebar's nav list -
the page's own items, Change Password and Log Out - all use the single class
`.sidebar-item`, so one rule covers them (confirmed in `PortalShell.tsx`). The
"Navigation" section label is not an item and has no line.

**Not applied literally, and why.** `border-image` replaces an element's whole
regular border. Every `.sidebar-item` already has `border-left: 3px solid
transparent`, and the active item recolours it (`border-left-color`) as its
accent. The supplied snippet would therefore have painted that left border blue
(the gradient's first colour) on every item and removed the active accent
altogether. The same visual - a 4px gradient line along the bottom of each item
- is drawn instead with `.sidebar-item::after` (absolutely positioned, inside
the item, `pointer-events: none`), with `position: relative` added to
`.sidebar-item`. It sits inside the item's box, so item heights do not change.
`border-image` remains used only by the banner's flag-coloured line, where there
is no competing border.

**Taken from the snippet vs left out.** Taken: the line itself - 4px, colours
`#00A3E0 -> #33CCFF`, now held in `--nav-item-line` in `:root`. Left out: the
`background-color: #ffffff`, `padding: 15px` and `border-radius: 8px`, which the
snippet itself labels as an example of the box's own look and "optional" - the
nav items keep their existing background, padding and square corners.

**Colour note.** The snippet's comment calls this "the Tanzanian flag gradient",
but its two colours are both blues, so that is what was implemented; the
banner's line is the green-black-blue one.

**Layout detail.** `left: 0` on the absolutely positioned line is measured from
the item's padding box, i.e. inside its 3px left border, so the line starts 3px
in from the item's outer left edge (visible next to the active item's accent).
It cannot be extended under the border: the item has `overflow: hidden`, which
clips at the padding box.

**Verified here:** one rule covers all three buttons (grep of the TSX); only my
`::after` and `--nav-item-line` were added, `border-image` appears only on the
banner; brace/paren balance (`index.css` 272/272, 306/306); backend compile
unaffected; a mock of the sidebar with five items rendered with a real
`:after` rule on an `overflow: hidden`, `position: relative` flex-like item -
the active item kept its left accent and gold gradient, every item showed the
line. (The mock engine does not support `var()`, so the gradient colours are
written inline there.) **Not verified here:** the real stylesheet in a real
browser. A first attempt at this edit failed an anchor match and wrote
nothing; this was caught by confirming the lines were actually present
before continuing.


## Fifty-second item — gradient line moved from the sidebar items to the dashboard cards; Automated Reports added to the sidebar

The fifty-first item misread the request. Its sidebar line was removed, and the
sidebar's item styling is back exactly as before (the `.sidebar-item` rule
region was diffed against an older delivered ZIP: 19 lines, identical). The
`--nav-item-line` variable became `--card-bottom-line` (same
`#00A3E0 -> #33CCFF`).

**Corrected reading.** "The navigation list" is the set of dashboard sections
the sidebar items lead to, and "jedwali" (table) is the white box. This fits
the supplied snippet's own class name (`.kipengele-cha-dashboard`, "dashboard
element") and its white background, padding and rounded corners, which describe
a card; and the "Automated Reports" box the request names is a card of buttons,
not a table - it contains no `<table>`. So the line is applied to every card in
the portals: `.portal-content .card`, i.e. 20 cards (11 on the BOT dashboard, 2
Institution, 7 Admin). Left out: the standalone Change Password card (outside
`.portal-content`), the KPI tiles, `action-card`s and the login card. The real
`<table>` elements were NOT touched; if tables were meant, that is a separate,
small change.

**How the line is drawn, and why not as supplied.** `.card` has a 1px border and
`border-radius: var(--radius)`. `border-image` replaces the whole border (the top
and sides too) and ignores border-radius, so the line would poke out square past
the rounded corners. Instead it is a background layer: `background-image:
var(--card-bottom-line)`, 100% x 4px, anchored bottom-left, `background-origin:
border-box`, with `border-bottom-color: transparent` so it shows through the 1px
bottom border and meets the card's outer edge. Backgrounds are clipped to the
rounded shape, so it follows the corners; it needs no `position` change on the
card (which could have shifted absolutely positioned descendants) and changes no
sizes - it occupies the bottom 4px of the card's own padding. The selector's
higher specificity (`.portal-content .card`) beats the card's `background:`
shorthand regardless of order. Checked first: no card has an inline background,
none is nested inside another (one Admin card has an inline `borderLeft` only,
which does not interfere).

**Sidebar addition.** `InternalPortal.tsx` gained `{ key: 'automated-reports',
label: 'Automated Reports' }` scrolling to `#reports-section`, placed second,
after Overview - the Automated Reports card is the first card on the page (line
566, right after the top anchor), and the sidebar is ordered like the page. The
existing last item "Download / Export" ALSO scrolls to `#reports-section`, so
two sidebar entries now lead to the same card; nothing was removed or renamed
unasked. BOT-only: the Institution and Admin portals have no automated reports
(RBAC tests: institution users cannot generate them).

**Verified here:** every edit confirmed present (and the removed ones confirmed
gone) by grep before continuing - the fifty-first item's first attempt had once
silently written nothing; `border-image` now appears only on the banner; the
sidebar rule region identical to the older ZIP; sidebar item order listed against
the page's section order; brace/paren balance (`index.css` 272/272, 308/308;
`InternalPortal.tsx` 545/545, 539/539); backend compile unaffected; before/after
mock of the Automated Reports card, including a zoom on the rounded corner (the
mock engine has no `var()`, so the gradient is inline there). **Not verified
here:** the real stylesheet in a real browser.


## Fifty-third item — card bottom line made very thin (1px) and light green

The owner confirmed the line is on the right elements (the dashboard cards) and
asked for it to be much narrower - "leave a quarter of the current thickness" -
and light green. Thickness went from 4px to 1px (4 x 0.25) and the colour from
`#00A3E0 -> #33CCFF` (blue) to `#7FDB85 -> #A6EBA2` (two light greens, kept as a
gentle left-to-right gradient like the earlier lines rather than a flat colour).

Colour and thickness now live in two `:root` variables (`--card-bottom-line`,
`--card-bottom-line-h`) and the rule reads `background-size: 100% var(
--card-bottom-line-h)`, so either is a one-place change. Comments describing a
"4px" line were updated. A side benefit of 1px: the card's bottom border is 1px
and already transparent (so the line shows through it), so the line now fills
exactly that border and sits on the card's outer edge instead of overlapping the
card's padding.

**It is subtle, as a consequence of "very narrow" plus "light".** Contrast
against the white card above it is 1.70 : 1 at the left end and 1.40 : 1 at the
right (the right end is paler), and 1.62 / 1.34 : 1 against the page background
below. In a before/after mock at real size the 1px line on one card was hard to
distinguish from the card's shadow just beneath it; at 4x zoom it was clearly
green on both cards. A slightly deeper green, or 2px, would make it read at a
glance - both are single-value edits.

**Verified here:** candidate greens' contrast computed; edits confirmed present
and the old blue / `100% 4px` values confirmed gone by grep; brace/paren balance
(`index.css` 272/272, 312/312); backend compile unaffected; before/after mock at
real size and a 4x zoom of two stacked cards (the mock engine has no `var()`, so
the values are inline there). **Not verified here:** the real stylesheet in a
real browser, where 1px lines on displays with fractional pixel ratios (e.g.
125%/150% scaling) can render slightly fainter or uneven.


## Fifty-fourth item — card line doubled to 2px in #0B3D2E; table headings #1C2326

**Card line.** Thickness doubled, 1px -> 2px (`--card-bottom-line-h`), and the
colour set to `#0B3D2E` (a dark forest green chosen from a swatch comparison),
replacing the light-green gradient. A flat colour is held in
`--card-bottom-line-color`; because the line is a `background-image` layer and
needs an image, `--card-bottom-line` wraps it as a one-colour `linear-gradient`.
The card's bottom border is 1px and transparent, so the 2px line now covers that
border and 1px of the card's padding above it (the 1px line had filled exactly
the border). Contrast of the line is 12.2 : 1 against the white card and 11.7 : 1
against the page background - the opposite of the previous light-green line
(~1.4-1.7 : 1) - so it now reads clearly.

**Table headings.** Set to `#1C2326` through a new `--table-heading-color`, by
changing the single global `th` rule (previously `var(--color-muted)`, `#64748B`,
4.76 : 1 on white; now 15.94 : 1). That covers the column headings of all 15
`<table>` elements in the project (Admin 5, Institution 3, BOT dashboard 7);
`th` font size, weight, case and letter-spacing were not touched.

**An ambiguity, resolved by checking the code.** "Headings of the tables" could
mean the card titles (the owner has been calling the dashboard cards "jedwali")
or the tables' own column headings. Card titles (`.card h2`) already resolve to
`#1C2326` exactly - they use `--color-primary-dark` - so setting them would have
changed nothing; the column headings were the grey ones that this request
visibly changes, so those were changed. Card sub-headings (`h3`/`h4`) still use
the general heading colour `#2B353A`, a near-identical shade, and were left
alone; matching them is a one-line addition if wanted.

**Verified here:** contrast ratios computed; edits confirmed present and the old
light-green values and the old `th` colour confirmed gone by grep; the one-colour
gradient and the nested `var()` rely on both custom properties being defined on
`:root`, where they are; brace/paren balance (`index.css` 272/272, 313/313);
backend compile unaffected; before/after mock of a card with a table (the mock
engine has no `var()`, so values are inline there). **Not verified here:** the
real stylesheet in a real browser.


## Fifty-fifth item — Validate and Flag as Bad Data take the pale-edged button look, keeping their green and red

Request: in Climate Quality Control - Readings Awaiting Review, give the Validate
and Flag as Bad Data buttons "the design of the other buttons" while keeping their
colours the same green and red.

**What was first understood, and the correction.** The owner asked to be told the
understanding before any change. The first reading - that "design" meant size
(the two buttons are the compact `btn-sm`, padding 6x12px / 12.2px text, while
standard buttons and the Approve/Reject in submission review are 10x20px / 13.4px)
- was wrong. The owner clarified that the other buttons are the ones that go white,
then gold, then white, and chose "also the gradient (pale ends, full colour in the
middle) for green and red". Nothing was changed before that correction.

**Implementation.** An opt-in class, `.btn-fade`, added to exactly those two
buttons (`InternalPortal.tsx`, the two `handlePromoteClimateGroup` buttons); a
project-wide change to `btn-success` / `btn-danger` would also have changed
Approve, Reject, and the Admin Activate / Deactivate buttons, which were not part
of the request. Four `:root` gradients: the CENTRE stop is the existing colour by
reference (`--color-success` `#10B981`, `--color-danger` `#EF4444`), and the hover
centres are the existing hover colours (`#0D9668`, `#DC2626`), so the colours
themselves are unchanged. The pale ends are white blended with 15% (left) and 8%
(right) of that colour - the same left/right asymmetry as the gold buttons' ends -
giving `#DBF4EC` / `#ECF9F5` (green) and `#FDE3E3` / `#FEF0F0` (red); hover ends are
those darkened 10%. The rules sit after the existing `.btn-success` / `.btn-danger`
rules: `button.btn-success:hover` and `button.btn-success.btn-fade` have equal
specificity, so source order decides, and the new `:hover` rules are more specific
than both.

**Text is now dark on these two buttons (a necessary side effect).** White text
would vanish on the pale ends (1.1-1.2 : 1), so the text uses `--color-primary-dark`
(`#1C2326`), as on the gold buttons. At the coloured centre this is an improvement,
not a loss: on green, white was 2.54 : 1 and dark is 6.28 : 1; on red, white was
3.76 : 1 and dark is 4.23 : 1 (still under the 4.5 : 1 guideline for small text,
though better than before). On the hovered red the centre is darker and dark text
falls to roughly 3.3 : 1.

**Deliberately unchanged:** the buttons' size (still compact `btn-sm`) - the
corrected request is about the colour pattern, not size; the ✓ and ✕ marks and the
button labels - they were not mentioned; every other green/red button.

**Verified here:** the pale-end colours and all contrast figures computed; `btn-fade`
confirmed by grep to be on exactly two buttons (InternalPortal 2, AdminPanel 0,
InstitutionPortal 0); brace/paren balance (`index.css` 276/276, 330/330;
`InternalPortal.tsx` 545/545, 539/539); backend compile unaffected; a mock of
before / after / hover beside a gold button and the unchanged Approve/Reject (the
mock engine has no `var()`, so values are inline there). **Not verified here:** the
real stylesheet in a real browser.


## Fifty-sixth item — the four tiles get a "Summary Figures" heading; Loan Data and Collateral Data merged in the sidebar

The group of four tiles (Total Loan Value, Total Collateral Value, Reporting
Institutions, Total Submissions) was the only block on the BOT dashboard with no
title; every other section is a card with an `h2`. After a recommendation to add
one, the owner chose the name "Summary Figures" and expected the two sidebar
entries that pointed here to be combined into one.

**Heading.** `<h2 className="section-title">🔢 Summary Figures</h2>` is the first
item in `#kpi-section`, spanning the whole grid like the existing approved-only
note, which stays directly beneath it. It is deliberately NOT wrapped in a card:
the tiles are themselves bordered, shadowed cards, so an outer card would nest
boxes. `.section-title` shares one rule with `.card h2` (same size, weight,
`#1C2326` colour, flex alignment), so the two cannot drift apart; it only adds
`margin-bottom: 0` because the grid's own gap supplies the spacing. Consequence:
since it is not a `.card`, it does not get the dark-green bottom line the cards have.

**Sidebar.** `Loan Data` (💰) and `Collateral Data` (🛡️) - both scrolled to
`#kpi-section` - are replaced by one `Summary Figures` entry at the same position
(between Dashboard Filters and Climate & Hazard Data, matching the page order). It
also now covers Reporting Institutions and Total Submissions, which had no entry.
The icon is 🔢 in both the sidebar and the heading: 📊, the icon first proposed for
the heading, is already used by Overview and Submission Status Distribution, and
a third use would have left three entries indistinguishable. Nothing else in the
code used the removed `loan` / `collateral` keys (searched). The sidebar goes from
14 to 13 entries. Only the BOT portal had these entries; the Institution portal is
unchanged.

**Wording kept consistent.** The Dashboard Filters note said "Narrow the KPI
cards, ..."; it now says "Narrow the Summary Figures, ...". The Automated Reports
note's "KPI summary" describes the content of the generated report, not this
dashboard section, so it was left alone.

**Verified here:** every edit confirmed present, and the removed entries and the old
wording confirmed gone, by grep; the sidebar listed in order and checked for
repeated icons (only the two pre-existing 📊 uses); brace/paren balance (`index.css`
277/277, 330/330; `InternalPortal.tsx` 546/546, 537/537); backend compile
unaffected; a layout mock showing Filters card -> heading -> note -> tiles (the mock
engine does not render the emoji and its tiles are a rough stand-in for the real
ones). **Not verified here:** the real stylesheet in a real browser.


## Fifty-seventh item — BOT sidebar reordered to follow the page's section order

Request: arrange the sidebar so it follows the same flow as the sections on the
main page - Automated Reports, then Dashboard Filters, then Summary Figures, then
Geospatial Map, and so on.

**Page order, checked against the code rather than assumed** (top to bottom):
Automated Reports, Dashboard Filters, Summary Figures, Geospatial Overview, Climate
Hazard Exposure Distribution, Climate Data Quality, Submission Status Distribution,
Combined Climate-Financial Exposure, Risk Advisory Reports, Submission Monitoring,
Climate & Financial Exposure by Region. The owner's description (the map follows
Summary Figures) matched.

**What moved.** The sidebar's 13 entries were reordered by editing the array, with an
assertion that none was added or removed. Two entries were out of place: Geospatial
Map was 12th and is now 6th, directly after Summary Figures; and Download / Export
was last. Download / Export leads to the same card as Automated Reports (the top of
the page), so listing it last made the sidebar jump back up the page; by the
page-order rule it now sits third, right after Automated Reports. Every other entry
keeps its relative position. Final order: Overview, Automated Reports, Download /
Export, Dashboard Filters, Summary Figures, Geospatial Map, Climate & Hazard Data,
Climate Data Quality, Submission Status Distribution, Combined Climate-Financial,
Risk Advisory Reports, Submission Status, Exposure by Region.

**Two things worth knowing.** (1) Automated Reports and Download / Export are
duplicates: two adjacent entries, one destination. Nothing was removed unasked; the
owner can merge or drop one. (2) Several sidebar labels do not match the page titles
they lead to: Climate & Hazard Data vs "Climate Hazard Exposure Distribution",
Geospatial Map vs "Geospatial Overview - Hazard Exposure & Portfolio", Combined
Climate-Financial vs "... Exposure", Submission Status vs "Submission Monitoring",
Exposure by Region vs "Climate & Financial Exposure by Region". Only the order was
requested, so no label was changed.

**Other pages checked, not changed.** The same check on the Institution portal
(Overview, Download Template, Upload Data, Submitted Files) and the Admin panel
(Password Resets, Institutions, Users, Audit Log) found both already in page order.

**Verified here:** a script maps each sidebar item to its target's line on the page
and confirms the sequence never goes backwards (True) - run on the working tree and
again on the file inside the delivered ZIP; brace/paren balance (`InternalPortal.tsx`
546/546, 537/537); backend compile unaffected. **Not verified here:** the real UI in
a real browser.


## Fifty-eighth item — "Download / Export" removed; the menu can be opened from the left edge of the screen

**Download / Export removed.** The owner asked why the entry existed, since it had no
visible function. It had none of its own: its only action was
`scrollTo('reports-section')`, the same target as "Automated Reports". The real
downloads - Summary Report (PDF), Summary Report (Excel), Summary Snapshot (Image) and
Combined Exposure (CSV) - are the four buttons inside that card. The docs do not record
when or why the label was added; that it was a leftover name for the reports card is an
inference from its identical target and absence of any function of its own. Removing it
loses nothing. The BOT sidebar now has 12 entries, in page order, with no two leading to
the same section (checked by script).

**Opening the menu from anywhere.** The hamburger lives in the page's top strip, so it
scrolls out of view; far down the page the only way to the sidebar was to scroll back up.
Checked first: the sidebar itself is already `position: fixed; top: 0; bottom: 0` with no
transformed ancestor (`.portal-shell` and `.portal-main` have no transform or filter), so
once opened it already appears wherever the page is scrolled to. Only the way to open it
was missing.

Added in the shared `PortalShell.tsx` (so it applies to the BOT, Institution and Admin
portals alike) and `index.css`: a 14px-wide zone fixed along the viewport's left edge
(`.nav-edge-trigger`, z-index 900, below the backdrop and sidebar at 1000/1001). Hovering
it fades in a soft shade along the edge and slides in a dark "Menu" tab at the cursor's
height; clicking anywhere on the zone or the tab opens the sidebar. The tab follows the
cursor's vertical position only while the pointer is on the thin strip itself (a ref
updated directly, not state, so the page does not re-render on every mouse move) and stays
put once the pointer is on the tab, so it cannot run away from the cursor. The tab's hover
persists because `:hover` applies when the pointer is over any descendant, even one
positioned outside its parent's box. The zone is not rendered while the menu is open.

**Deliberate limits.** (1) Mouse only: `@media (hover: none)` removes the zone on touch
devices, where there is no hover and an invisible strip would only swallow taps - so on a
phone the hamburger remains the only opener. (2) `aria-hidden`: it is a pointer
convenience; the hamburger stays the accessible control. (3) The tab overlays the page's
left content briefly while hovered. (4) The zone intercepts clicks in the 14px at the very
left edge; page content starts at least ~28px in, so nothing is covered today.
`prefers-reduced-motion` disables the transitions.

**Verified here:** every edit confirmed present, the removed entry confirmed gone, by grep;
the sidebar order and the no-duplicate-target property checked by script; brace/paren
balance (`index.css` 286/286, 340/340; `PortalShell.tsx` 55/55, 58/58;
`InternalPortal.tsx` 545/545, 535/535); backend compile unaffected; a two-panel mock of the
hover hint and the in-place sidebar. **Not verified here:** the interaction in a real
browser - the cursor following, the tab staying hoverable, the click opening the menu -
which is reasoned from the CSS and React code, not run.


## Fifty-ninth item — the pale-edged look applied to every coloured button, not just Validate / Flag

The owner noticed the Activate / Deactivate buttons in the Admin Users and Institutions
tables did not have the pale-edge-then-colour-then-pale-edge look, and asked for it on
every clickable button that has a colour.

**Change.** The fifty-fifth item's opt-in `.btn-fade` class was removed (from the two
buttons and from the stylesheet) and its effect made the default: `button.btn-success`
and `button.btn-danger` now use `--success-fade` / `--danger-fade` (and the `-hover`
variants) directly. The green and red themselves are unchanged - they are the centre stop
(`--color-success`, `--color-danger`; hover centres `#0D9668` / `#DC2626`). Because every
use goes through those two classes, this covers all 8 green/red buttons in the project:
Admin Users and Institutions Activate/Deactivate (their classes are chosen by a template
string, which the stylesheet change reaches without touching the TSX), the Admin password
reset Approve/Reject, the BOT submission-review Approve/Reject, and Validate / Flag as Bad
Data.

**How "every" was established, not assumed.** All 46 `<button>` elements were classified
by the look the stylesheet now gives them: 35 have the pale-edged look (21 generic buttons
and 6 gold-class buttons that already did, plus these 8); 11 have no fill by design - the
icon and text controls (hamburger, sidebar close, notification bell, "Mark all as read"),
the sidebar items (the active one is a gold fade), the three outline `btn-secondary`
buttons, and one inline-transparent back link. Zero flat filled-colour buttons remain. The
only other flat green/red backgrounds in the stylesheet are the status badges
(`.badge-valid` etc.), which are not clickable. Several clickable classes in the
stylesheet (`.pill-tab`, `.logout-button`, `.quick-action-card`, `.file-button`, ...) are
used nowhere in the TSX and were left alone.

**Text is dark on all green/red buttons now** (was white): white would vanish on the pale
ends (1.1-1.2 : 1). Contrast at the coloured centre: green 2.54 -> 6.28 : 1, red 3.76 ->
4.23 : 1 (still under the 4.5 : 1 guideline for small text, though better than white).

**Left as they are, on purpose:** the outline `btn-secondary` buttons (no fill, so no
colour to fade); the dark "Menu" tab of the left-edge opener (fiftieth-eighth item) - it
is a filled, clickable element, but white text on a fade would be unreadable at its ends,
and it is a navigation aid rather than an action button; say if it should be included.

**Verified here:** the CSS and TSX searched to confirm no `btn-fade` remains and that
every variable the rules use is defined; the 46-button classification above; brace/paren
balance (`index.css` 282/282, 338/338; `InternalPortal.tsx` 545/545, 535/535); backend
compile unaffected; a mock of the Admin tables and the Approve/Reject buttons. **Not
verified here:** the real stylesheet in a real browser.


## Sixtieth item - database review: four fixes (missing constraints, backup, first administrator, database access)

A review of the database (code, migrations, `docker-compose.yml`; the live database was not
available) found the design strong - `Numeric(20,2)` money, 29 CHECK constraints, partial unique
indexes, version lineage, no string-built SQL - and four things to fix before real data goes in.
Everything below was written without Docker, PostgreSQL, SQLAlchemy or pytest in the environment;
what was executed and what was not is stated at the end.

**1. Three CHECK constraints existed only in the code.** `ck_submission_records_outstanding_le_loan`,
`ck_submissions_record_counts_consistent` and `ck_submissions_version_number_positive` are declared in
models.py but created by no migration (searched by name and by rule text). The tests build their SQLite
database from models.py, so they had the rules and passed; the real PostgreSQL database, built only by
migrations, did not - the same drift as 9c1852419557. New migration `f4a9c2d71b05` adds them, safely on a
database that already holds data: on PostgreSQL `ADD CONSTRAINT ... NOT VALID` (enforced for every new
or changed row) then `VALIDATE` at once if no old row breaks it; if some do, it logs the count and the
query to find them and leaves it NOT VALID. A plain ADD CONSTRAINT would have scanned every old row and,
because init_db.py runs migrations at container start, a single bad historical row would have stopped the
backend from booting. Nothing is deleted or rewritten. `scripts/verify_db_constraints.py` did not list
these three either (nor `ck_climate_records_reporting_period_format` and
`uq_submission_records_submission_loan`); it now lists all 33 protections and warns about constraints
still NOT VALID. New `tests/test_schema_parity.py` (5 tests, no database) fails if a constraint declared in
the models is created by no migration, if the verify script misses a declared protection, or if the
migrations stop forming one linear chain - it was shown to fail when the new migration is removed.

**1b. The validator had to change with it (KG-05).** Run against 8 bad rows before any change, the
validator kept the bad value even where it flagged the row: a negative loan amount (flagged, -5 stored),
a negative insurance value, a negative annual turnover, an interest rate of 150 or -2, a latitude of 200,
a longitude of 500 were stored as given - and the database CHECK then rejects the whole INSERT, so the
upload fails with an unexplained HTTP 409 instead of showing a row error; outstanding > loan was accepted
as VALID. Amounts of 1e18 or more were accepted too, which would overflow `Numeric(20,2)` in PostgreSQL
(a server error; SQLite does not enforce it, so the SQLite tests could never show it). Now each such
value is reported as an ERROR on its row and NOT stored, so the row is still persisted for the reviewer
(FR-SUB-07) and the database never sees a value it would reject. Outstanding == loan and a large-but-
representable amount (5e17) are still accepted. Verified by running the real validator over every case
before and after; the system's own downloadable template (with its example row) validates identically
under the old and new code. 12 new upload tests (`test_upload_database_rules.py`).

**2. No backup.** `scripts/backup.ps1|.sh` and `restore.ps1|.sh` back up the database (pg_dump custom
format, checked readable) AND the uploaded files together, with SHA256SUMS verified before a restore, a
typed RESTORE confirmation, and the backend stopped during the database restore. The dump is made inside
the container and copied out with `docker compose cp`, because piping binary data through PowerShell
corrupts it. Old backups are never deleted by the scripts. See `docs/DATABASE_OPERATIONS.md` (new).

**3. No first administrator in production.** `init_db.py` seeds nothing when ENVIRONMENT=production (the
demo passwords are published) and the only user-creation endpoint needs an administrator already signed
in, so a fresh production database had tables and no way to log in. New `app/services/admin_bootstrap.py`
(testable logic) and `scripts/create_admin.py` (hidden password prompt, never a command-line option);
refuses a weak password, a bad e-mail, a taken name, or an already-existing active administrator unless
`--allow-additional` (the lockout-recovery path); audited as ADMIN_BOOTSTRAPPED without the password.
`init_db.py` now prints the command when production starts with no users. 12 new tests
(`test_admin_bootstrap.py`).

**4. The database was open to the network and used as a superuser.** The port is now published as
`127.0.0.1:5433` (it was `5433:5432`, i.e. every interface; the backend uses `db:5432` internally and never
needed it). A restricted runtime role is provided as an OPT-IN, so the existing setup keeps working:
`database/roles/create_app_role.sql` (no superuser, no DDL, no DELETE - the application issues none,
checked by search - and no UPDATE on `audit_logs` / `risk_advisory_notes`, turning "append-only" from the
application's promise into something the database enforces),
`docker-compose.hardened.example.yml` (copy to `docker-compose.override.yml`), and
`MIGRATION_DATABASE_URL` support in `alembic/env.py` so migrations still run as the owner. Default
behaviour is unchanged when it is unset.

**Stale advice corrected.** The README told readers to run `docker compose down -v` (deleting the
database and the uploaded files) "whenever the models or docker-compose.yml itself change" - a leftover
from before migrations existed, and this very change edits docker-compose.yml. It now says to rebuild and
restart, that migrations keep the data, and not to use `-v` on real data. The README also points to the
first-administrator step.

**Honest limits.** Not done: encryption at rest or TLS to the database, row-level security, retention of
old tokens/notifications/audit rows, time-zone-aware timestamps, case-insensitive user names (listed in
`docs/DATABASE_OPERATIONS.md`, section 6).

**Executed here:** the validator on 12+ cases, old versus new, and on the generated template; the 5
schema-parity tests (5/5 pass, and shown to fail without the migration); YAML parse of both compose files
and a simulated merge of the override; `bash -n` on both shell scripts; py_compile on every Python file;
an AST call-signature cross-check (no mismatched keywords); a static check that every name, keyword and
model column the new code and tests use exists. **NOT executed:** the new migration against PostgreSQL;
the 24 new database-backed tests (upload rules and bootstrap - they need the full stack; expected suite
size 181 + 29 = 210 collected, 208 passed, 2 skipped); the backup and restore scripts, and the two
PowerShell files could not even be parse-checked (no PowerShell here); the role SQL. Run the restore drill
in `docs/DATABASE_OPERATIONS.md` before relying on the backups.


## Sixty-first item - decision-support additions: hazard filter, KPI lineage, row validity, hazard matrix, summary draft

Five additions, all drawn from data the system already holds and all within the ICN; none needs new
data from BOT. Chosen after a review of suggested additions that rejected anything inventing policy
(risk scores with Low/High thresholds, "+20%" scenarios, "overdue" without BOT deadlines).

**1. Hazard filter (ICN item 9; closes KG-10).** `filter_hazard_type` (Flood, Drought, Landslide,
Cyclone, None; anything else is HTTP 422) on hazard-exposure, combined exposure, map-points and the four
report endpoints, and a fourth control in Dashboard Filters. Semantics, chosen to avoid double counting:
Hazard Exposure and the map classify each region/period under ONE dominant recorded hazard, so the filter
keeps the regions whose dominant hazard matches; Combined Exposure keeps the regions where the hazard is
among those recorded. It deliberately does NOT narrow the Summary Figures, the IDW hazard surface (which
needs every region) or the loan and collateral points (they carry no region); the screen says so, and the
reports state the active hazard filter in their "Filters applied" line. (An earlier note in the review
conversation suggested a loan could be counted under two hazards; that is not so for Hazard Exposure.)

**2. KPI data lineage.** New `GET /api/analytics/kpi-sources`: one row per current APPROVED submission behind
the figures (institution, period, file and version, rows used, loan and collateral totals, row validity),
built on the same base query as every calculation so it cannot disagree with the KPI. "View the source of
these figures" under Summary Figures lists them with a totals row, and "View rows" opens the existing
submission detail with its rows and loan numbers. Same tenant scoping; the administrator is refused.

**3. Row validity.** valid rows / total rows, shown in Submission Monitoring and in the lineage table. Named
"row validity", not a quality score: a score needs weights and thresholds that are BOT's to set; it is a
descriptive ratio and is never combined with risk.

**4. Hazard exposure matrix.** Hazard x loan exposure x collateral x records x regions, grouped on the
client from the Hazard Exposure rows already loaded. The "Institutions" column from the original suggestion
is not in the data, so it is "Regions". No new hazard type was added.

**5. Editable supervisory summary.** "Generate Supervisory Summary" writes a draft into a text box from the
approved figures on screen (scope, exposure, hazard pattern, concentration, climate-data quality,
submission tracking). Every sentence states a measured value; there is no period-over-period comparison, no
rating, no estimate. The analyst edits it; it is not saved or sent.

**Tests added (not yet run by the author):** `test_hazard_filter_and_kpi_sources.py`, 10 tests - filter on
each of the three analytics views, unknown value refused, KPI totals unchanged by the hazard filter, reports
honour the filter (CSV content, and PDF, Excel and PNG generate), lineage lists only current approved
submissions and matches the KPI total, follows the filters, is tenant-scoped, administrator refused.

**Verification here.** py_compile of every touched backend file; an AST check that every keyword passed to
the patched functions is a real parameter; the dashboard source type-checked with the TypeScript compiler
(strict, with stand-ins for react and the project's own modules): no diagnostics, before and after, and the
checker was shown to catch a deliberately introduced typo. NOT verified: the pytest run (10 new tests; the
suite should now collect 220), `docker compose build`, and the screens in a browser.


## Sixty-second item - hazard filter linked to the map; hazard-focus line; full-width supervisory button

Raised by the project owner while testing: choosing a Region in Dashboard Filters visibly changed the
Geospatial Map, but choosing a Hazard appeared to do nothing.

**Cause (read from `HazardMap.tsx` and `InternalPortal.tsx`, not assumed).** The dashboard passed the map
the institution, region and reporting-period filters but not the hazard. The hazard filter only trimmed the
list of region markers on the server side. The map's own "Hazard layer" selector is separate and starts
empty, so no hazard surface appeared. And when no region had the chosen hazard as its dominant recorded
hazard, the marker list was empty and the whole map was replaced by "No geolocated exposure data yet", which
was misleading: the data exists and the filter reduced it to zero. This is the divergence between the
dashboard control and the map control that was foreseen when the hazard filter was designed.

**Changes (frontend only; no backend, schema or test change).**
1. `HazardMap` accepts `filterHazardType` and, when it is set, selects the same hazard layer ("None" clears it);
   clearing the filter leaves the analyst's own layer choice alone. The dashboard passes it in.
2. The map stays visible under a hazard filter and states what the filter did: how many region markers match,
   or that no region has that dominant recorded hazard, and that the hazard surface and the loan and collateral
   points are not narrowed by hazard.
3. A labelled "Hazard focus" line under Summary Figures when a hazard is chosen: loan exposure and collateral in
   the regions whose dominant recorded hazard is the chosen one, with its share of the total loan value. It is
   the existing Hazard Exposure total, now visible next to the headline figures. The four Summary Figures
   themselves are deliberately still NOT narrowed by hazard (hazard is recorded per region; a "flood total"
   would be read as loans hit by floods); the line says so. Narrowing the four figures by hazard was
   considered and left for after the demonstration: it changes the backend KPI calculations and needs tests.
4. In Automated Reports the "Generate Supervisory Summary" button now spans the full width of the card, below
   the four report buttons, which are unchanged (2 x 2 grid).

**What the hazard layer actually shows (clarified, and the presentation wording corrected).** The surface is
not a map of flood or drought intensity. Its values are the loan exposure (TZS) of the regions in which the
chosen hazard is the dominant recorded one, interpolated by IDW with every other region anchored at zero. It is
a picture of exposure under a hazard classification. Combined with a financial layer (Loan or Collateral dots
at the submitted coordinates) it lets an analyst see, for example, collateral locations against exposure under
Flood.

**Verification here.** The frontend type-checked with the TypeScript compiler (strict, stand-ins for react,
axios and leaflet): 45 diagnostics before and 45 after, all stand-in noise, none new. The checker was shown to
catch three deliberate mistakes in the new code: a misspelt property, an unknown prop passed to the map, and a
prop of the wrong type. An earlier version of the check did NOT validate component props; the stand-ins were
corrected and the result above is from the corrected check. **NOT verified:** `docker compose build` with the
real React types, and the screens in a browser (layout of the full-width button, the map messages).

## Sixty-third item - "View Details" froze the browser

Reported by the project owner: pressing the many View details / View rows buttons made the page
stick until the browser offered "Exit page".

**Cause (read from the code, not assumed).** The submission detail endpoint returned every row and
every finding of the submission (`return submission`), and the panels drew all of them at once
(`records.map(...)` and `errors.map(...)`). A 15,000-row file is about 165,000 table cells, so the
browser's main thread blocked and Chrome showed "Page unresponsive - Exit page / Wait". The same
panel is opened by Submission Status (View Details), by the source-of-the-figures table (View rows)
and, in the institution portal, by Review. A second cause of confusion: the panel is at the bottom
of the page while the button is higher up, so even when it opened the user did not see it.

**Fix.**
1. Backend, GET /api/submissions/{id}: new optional query parameters `record_offset`, `record_limit`
   (default 100, maximum 500), `error_offset`, `error_limit` (same); the response carries one page of
   rows and one page of findings in a stable order (row number) plus `records_total` and
   `errors_total`. Authorisation is unchanged and is checked before any row is read. Upload and review
   responses are unchanged.
2. Frontend, both portals: the panel loads 50 rows and 50 findings at a time and pages them with a new
   PagerBar ("Showing rows 1 to 50 of 15,000", Previous, Next); the panel scrolls itself into view when
   opened; a Close button was added at the top of the panel.
3. Six tests in test_submission_detail_pagination.py: default page and totals, ordered pages that
   together are the whole submission, findings paged independently of rows, a page beyond the end is
   empty, unreasonable parameters refused (HTTP 422), owner can page and another institution is refused.

**Verification here.** Backend files compile; test imports and fixtures exist; the frontend type check
shows the same 45 stand-in diagnostics before and after, none new, and a deliberate wrong prop type was
caught. **NOT verified:** the six new tests have not been run (the suite should now collect 226), the
Docker build with the real React types, and the behaviour in a browser on a large file.


## Sixty-fourth item - audit log filters as drop-downs

Requested by the project owner. The audit viewer had one free-text box for the action; the
backend already filtered by action, entity type and user.

**Change.** Three drop-downs (Action, Entity type, User) that apply as soon as one is chosen, a Clear
Filters button, an Export button that says whether it exports all or the filtered entries, a count of
matching entries and a User column. The options come from a new administrator-only endpoint,
GET /api/audit-logs/filter-options, which lists the actions, entity types and users that actually
occur in the audit log, so a filter can only name something that exists (a typed filter that matches
nothing looks exactly like an empty log). The endpoint count is now 52 (51 under /api plus health).

**Tests.** Four, in test_audit_filter_options.py: each value listed once and in order, no empty values,
every offered value works as a filter, only the administrator may read the options (HTTP 403 and 401).

**Not verified here.** The four new tests have not been run (the suite should now collect 230 with the
detail-paging tests), the Docker build with the real React types, and the screen in a browser.


## Sixty-fifth item - the supervisory summary can be closed

Reported by the project owner: Generate Supervisory Summary opened the draft well, but it could not
be closed without refreshing the page. The panel was shown whenever the draft text was non-empty and
nothing could empty it.

**Change.** An explicit open or closed state for the panel (frontend only). A Close button sits at the
top of the draft and another beside Copy; the text area stays editable and no longer controls whether the
panel is shown. Closing discards the draft (it is never saved or sent) and Generate writes a fresh one.

**Verification here.** Braces and parentheses balance; the frontend type check shows no new diagnostics.
**Not verified:** the behaviour in a browser.

## Sixty-sixth item - three workflow rules enforced by the database

Raised from the database analysis: three rules held only because the application kept them.

**Added (migration b5d8a3c6e102, head after f4a9c2d71b05).**
1. `ck_submissions_current_only_valid_or_approved` - only a VALID or APPROVED submission can be current.
2. `ck_submissions_reviewer_not_submitter` - the reviewer is never the person who uploaded it (BR-03).
3. `ck_users_institution_user_has_institution` - an institution user belongs to an institution (BR-15).
The protections the verification script expects go from 34 to 37 (CHECK constraints 29 to 32).

**Why the third rule is one-way.** The reverse (staff roles must have no institution) was designed first
and withdrawn: the demonstration seed (`init_db.py`) attaches the administrator and the BOT analyst to the
BOT institution record, although the API refuses that combination. An existing database holds those rows,
and PostgreSQL checks a NOT VALID constraint on every UPDATE of an existing row, so every sign-in (which
updates `last_login_at`) would have failed for those two accounts. Recorded as a finding: the seed does not
follow the API's own rule; harmless today, to be aligned later.

**Safety.** Each rule was compared with every code path that writes the columns (upload, supersession,
approve, reject, fallback restoration): status and `is_current` change in one UPDATE, the reviewer is set only
after the maker-checker refusal, and only institution users can upload. On PostgreSQL the constraints are
added NOT VALID and validated at once when no existing row breaks them; otherwise the count is logged and
nothing is deleted. The three conditions and the "rows that break it" queries were exercised on SQLite with
accept, reject and NULL cases.

**Tests.** `test_workflow_constraints.py` (11 cases). `make_user` in the test helpers now gives an
institution user an institution when none is passed (21 existing calls built users the database now refuses).

**Not verified here.** The new tests and the migration on PostgreSQL have not been run (the suite should
collect 241), nor `verify_db_constraints.py` (should report 37). The report and the presentation still state
the last verified figures (29 CHECK constraints, 34 protections, 7 migrations) and are to be updated after
the run.

## Sixty-sixth item - production environment (stage 1 of the full-deployment work)

Requested by the project owner after the prototype was accepted: build the environment for a full
deployment, so that the next session can connect the Bank's systems and the climate-sector data directly.
The first condition was not to break the working system.

**How it is kept safe.** Everything is new and separate: `docker-compose.prod.yml` (project name `cdr-prod`,
volumes `cdr_prod_*`), `frontend/nginx.prod.conf`, `.env.production.example`, `scripts/prod_setup.py`,
`scripts/check_production_config.py`, `scripts/prod_up.ps1` and `.sh`, `docs/PRODUCTION_DEPLOYMENT.md`. The
development `docker-compose.yml`, `frontend/nginx.conf` and `backend/Dockerfile` are byte-identical to the delivered
ones. The only application change: in production FastAPI does not serve `/docs`, `/redoc` or `/openapi.json`
(`api_docs_urls()` in `startup_checks.py`, three-line change in `main.py`, 8 test cases).

**What it provides.** Only ports 80 and 443 open; HTTPS with HTTP redirected and HSTS; no demonstration accounts;
secrets generated at random into `.env.production` (ignored by git, with `certs/`); the restricted database role enabled
by a staged start; log rotation; health checks with start order by health; a configuration checker that refuses weak or
placeholder settings, a published database or backend port, development volumes and a missing certificate.

**Verification here.** Compose and nginx files parse; the checker and the generator were run on a copy and caught every
deliberate fault (weak and short secrets, a published database port, a missing git-ignore entry, missing certificate);
all Compose variables are defined in the example; `bash -n` accepts `prod_up.sh`; the backend compiles.
**Not verified:** a real start with Docker, the TLS handshake with a real certificate, the staged role switch, and
`prod_up.ps1` (no PowerShell available). The 8 new test cases have not been run (the suite should now collect 249).


## Sixty-seventh item - verification run on the owner's machine (6 October 2026)

Run by the project owner on the delivered stack (before the production files were added):
`docker compose down`, `build --no-cache` (142 s; the frontend compiled in 8 s with the real React types), `up -d`
(database healthy, backend and frontend started); the backend log shows no `NOT VALID` constraint; `pytest`:
**241 collected, 239 passed, 2 skipped, 0 failed** (the two skips are the known ones in test_startup_checks);
`verify_db_constraints.py`: **all 37 expected CHECK constraints and unique indexes present on the real database**.
This verifies migration b5d8a3c6e102 on PostgreSQL (the three workflow constraints were added and validated), the
paging of submission details, the audit filter options and the workflow-constraint tests.

`backup.ps1` did not run: PowerShell refused it as "not digitally signed" (execution policy), so no backup was
taken before the rebuild; the data volume was kept (`down` without `-v`). The fix is documented in
DATABASE_OPERATIONS.md and PRODUCTION_DEPLOYMENT.md (`Unblock-File` or `-ExecutionPolicy Bypass`).

The report and the presentation still state the figures of the earlier verified run (220 tests, 29 CHECK constraints,
34 protections, 7 migrations); they are to be updated once, after the next run, which will include the 8 production-config
test cases (249 collected).

## Sixty-eighth item - create_admin crashed after creating the administrator

Found by the project owner creating the first administrator on the production stack: the command ended with a
`DetachedInstanceError` traceback. **The administrator had been created** (committed, and the ADMIN_BOOTSTRAPPED audit
entry written); only the final message failed.

**Cause.** `scripts/create_admin.py` closed its database session in a `finally` block and then printed
`user.username`. The audit step commits, which expires the user's loaded fields, so after `db.close()` reading the
field tried to reload it through a session that no longer existed. The 12 bootstrap tests keep their session open for
the whole test, so they could not see it.

**Fix.** The script reads the username while the session is still open; the service reloads the user after the audit
commit (`db.refresh`) so the returned object stays readable after a close. New test
`test_the_returned_user_is_still_readable_after_the_session_is_closed` (closes the session, then reads the user).

**Not verified here.** The new test has not been run (the suite should now collect 250 with the production-configuration
tests) and the script was not run against the production stack after the fix. The account that was created before the
crash is valid and unaffected.


## Sixty-ninth item - production backup, retention, restore drill and schedule (stage 2 of the full-deployment work)

**Why a new tool.** The existing backup and restore scripts call `docker compose` without a project or file, so they serve the
development stack; and a backup that has never been restored is not proven. `scripts/prod_ops.py` (Python 3, Docker, Windows and
Linux) adds, for the production stack only: `backup` (same layout as `backup.ps1`, checks its own result, optional off-machine
copy that is also checked, retention that removes only timestamp-named folders and never the new one), `status` (age and integrity,
exit code for monitoring), `drill`, `restore` and `schedule`.

**The drill** restores a backup into a throw-away copy (project `cdr-drill`, own volumes, no ports): creates the bare role cdr_app,
restores the dump, re-applies the least-privilege grants, starts the backend, restores the files, then checks the protections, the
rows, that cdr_app still cannot update the audit log or delete submissions, and the file count; it prints the time taken; it removes the
copy even when a check fails. Every command names `-p cdr-drill`, and the only destructive command refuses any other project.
`restore` (production) needs the typed phrase RESTORE-PRODUCTION, refuses a damaged backup, and takes a safety backup first.

**Found on the way.** `backups/` was not in `.gitignore` although a backup holds real data; it is now. `database/roles/create_bare_role.sql`
is new: a backup taken on production carries grants for cdr_app, and restoring them where the role does not exist would fail.

**Verification here.** Run against a fake `docker` that records every command: three backups with `--keep 2` leave two; the off-machine copy
is checked; a damaged dump is reported by `status` (exit 1) and refused by `drill` and `restore` (nothing issued); a healthy drill passes;
a drill with wrong cdr_app rights FAILS (exit 1) and still removes its copy; no command anywhere combined `down` or `-v` with `cdr-prod`;
restore with a wrong phrase issues no command; restore with the right phrase takes the safety backup first, then restores in order.
**Not verified:** a real run with Docker (the PostgreSQL behaviour of `pg_restore --clean --if-exists --no-owner` into the drill copy),
and the Windows `schtasks` registration.

## Seventieth item - verification of the production environment on the owner's machine (6 October 2026)

Run by the project owner after items 66 and 69. **Verified on real Docker, PostgreSQL 16 and Windows:**
- `prod_setup.py`, `check_production_config.py` and the four stages of `prod_up.ps1` (the stack was built and started; the
  restricted role cdr_app was created with its revokes; the backend was switched to it; the web server started). Three problems were
  found and fixed on the way: the configuration checker needed the `yaml` module (rewritten to need none), `create_admin` crashed after
  creating the administrator (item 68), and the PowerShell execution policy blocks unsigned scripts (documented).
- The production database holds exactly one user (the administrator you created) and no demonstration accounts; all 37 protections are
  present; the backend connects as `cdr_app`; HTTP is redirected to HTTPS (301); `/openapi.json` returns the web application, not the
  API description; HSTS, nosniff, X-Frame-Options and Referrer-Policy are sent; only ports 80 and 443 are published (the database and the
  backend are reachable only inside the network); all three services report healthy. Sign-in and the administrator panel work over HTTPS
  with a self-signed trial certificate.
- `prod_ops.py`: `backup`, `status`, `schedule` and `drill` ran; both drills PASSED (see BACKUP_AND_RECOVERY.md).

**Not yet verified:** `prod_ops.py restore` against the production stack (destructive; to be rehearsed on an agreed date), a real
certificate from the Bank's ICT, the scheduled task actually firing at 02:00, and the latest development test run after the
production-configuration changes (the suite should now collect 250). The report and the presentation still state earlier figures.


## Seventieth item - a missing off-machine destination crashed the backup (found on the owner's machine, 7 October 2026)

Verification run of the owner on 7 October 2026: the development stack rebuilt (92 s) and `pytest`: **250 collected, 248 passed,
2 skipped, 0 failed**; the restore drill passed a second time on the production backup (31 s) and on the 15 MB development
backup (36 s); the daily task "CDR-Backup" was registered; `status` reported two backups with integrity OK.

**Found.** `python scripts/prod_ops.py backup --copy-to D:\cdr-backups` ended in a FileNotFoundError traceback because the
machine has no D: drive. The local backup had been made, but the traceback hid that, retention did not run, and the re-registered
daily task now pointed at the missing drive.

**Fix.** An off-machine copy that cannot be made is now a clear warning (what failed, that the local backup is safe), not a crash:
the local backup stands, retention runs, `backup.log` records `COPY-FAILED`, the exit code is 1 so a scheduler or monitor can see
it, and `status` keeps warning until a copy succeeds. Tested against a destination that cannot exist: local backup kept, retention
still removes the oldest, status warns (exit 1); against a good destination: the copy is checked, the log says OK, status exit 0.

**Not verified.** The fixed tool on the owner's Windows machine. The report and presentation still carry earlier figures
(220 tests, 29 CHECK constraints, 34 protections, 7 migrations) and say nothing yet of the production stack, the backup tool or
the drill: they are to be updated once, with the verified figures above (250 / 248 / 2; 32 CHECK, 37 protections, 8 migrations).

## Seventy-first item - report and presentation brought up to the verified state (7 October 2026)

The report (99 pages) and the presentation (87 slides) now state the figures verified on the owner machine: **250 test cases,
248 passed, 2 skipped by design, in 108 seconds (25 modules)**; **37 database protections** present on the development database,
the production database and every restored drill copy; **8 migrations**, one head; **52 endpoints**.

New in the report: Section 4.15.4 (the production environment, Figure 4.10, Table 4.15), the backup and drill tool in 4.15.2, Section 5.11
with Tables 5.11 and 5.12 (production checks and four restore drills), four more defects in Table 5.8, the revised recommendations
and the pilot stage, Appendix H screens S-26 to S-28 and Appendix I.4. New in the presentation: the production environment slide, the
restore drill slide, a rewritten backup slide, and the updated path to production and roadmap.

**What both documents still say honestly:** the production environment was checked with a self-signed certificate on one machine with sample
data; no off-machine copy of a backup exists (the machine has one drive); the real restore command has not been run; the SRS (version 1.4)
does not yet contain the production and backup additions.

## Seventy-second item - read-only keys for external systems (stage 3 of the full-deployment work)

**Why.** The Bank wants QGIS, ArcGIS, TMA, BSIS and RTIS connected. Those are systems, not people: they cannot sign in with a password that
expires, and the system had no machine-to-machine access. This stage adds the foundation, not the connectors that bring TMA and PMO data in.

**Design decisions.** (1) A key is created by a BOT analyst, never by the System Administrator, who may not read supervisory data (a key
would be a way round that rule); the administrator may list and revoke keys as an emergency control. (2) Keys have their own endpoints
(`/api/integration/...`, GET only) and are refused everywhere else, so no existing endpoint changed and a key can never write. (3) The endpoints call
the same analytics functions as the dashboard, with sector-wide scope, so the numbers cannot differ from the screen. (4) The key is shown once and never
stored (SHA-256 hash only); every refusal gives the same message while the audit log records the real reason; every successful read is audited
with the client, path, filters and row count, never the key. (5) A key always expires (1 to 365 days) and revoking is immediate.

**Built.** Table `api_clients` (migration `c6e9b2d4f713`; four CHECK constraints and two unique indexes, so the verification script now expects
43 protections: 36 CHECK, 6 unique, 1 column); `app/core/integration_auth.py`; `app/api/integration_clients.py` (create, list, revoke) and
`app/api/integration.py` (whoami, kpi-summary, hazard-exposure, combined-climate-financial-exposure, map-points, exposure-points and a GeoJSON
variant); the Integration Access section on the analyst page (create, list, revoke) and the administrator page (list, revoke); docs/INTEGRATION_ACCESS.md.
The suite is expected to collect **282** cases (250 + 32 new).

**Verification here.** The key-handling code was run against stand-in modules: 18 of 18 checks (format, both header forms, wrong, unknown, malformed,
revoked and expired keys, a sign-in token refused, the audit contents, no secret in any audit entry, the rate-limit bucket). The static parity tests pass (5 of 5);
the parameters the endpoints pass match the service functions; the type check shows only the usual stand-in noise (+3) and a deliberate typo was caught.
**Not verified:** the 32 new tests, the migration on PostgreSQL, the Docker build with the real React types, the screen in a browser, the per-key rate limit
(the limiter is off in the test suite) and the QGIS and ArcGIS snippets.


## Seventy-third item - keys that send climate files (stage 4 of the full-deployment work)

**Why.** The Bank wants TMA and PMO data to arrive without an analyst uploading each file. Neither organisation has agreed an interface (TMA_INGESTION.md), and
inventing one would be wrong. What can be built honestly is the receiving side: a door that accepts the same file the analyst uploads, for a system that holds a key.

**Design decisions.** (1) A key has one scope: READ (as before), INGEST_TMA or INGEST_PMO. A sending key reads nothing, not even the dashboard figures, and a reading key
sends nothing; using a key for the other job is refused with 403 and audited. (2) The source label (`API_KEY_TMA`, `API_KEY_PMO`) comes from the key and cannot be chosen by
the sender; the manual upload refuses these two labels. The label names the channel, not a verified sender. (3) One shared implementation (`climate_upload_service.py`)
validates and stores a file for both the analyst and the key, so they can never validate differently; the analyst endpoint behaves exactly as before (the extracted steps are the old ones). (4) Everything
delivered is stored UNVALIDATED: it enters the analysis only when an analyst promotes it, so no feed can change a dashboard figure by itself. (5) Sending the same file again is
safe (duplicates are reported, nothing is overwritten). (6) Provenance: a batch records the key (`uploaded_by_api_client_id`) or the person, never both (a CHECK); the audit log
gets `INTEGRATION_INGEST` with the key name, file and counts; BOT analysts are notified. (7) Limits: the upload size and row limits of the manual upload, 30 files a minute per key.

**Built.** Migration `d7f1a3c5e824` (column `api_clients.scope`; column `climate_ingestion_batches.uploaded_by_api_client_id` with its foreign key and index; two CHECK
constraints, so the verification script now expects **45 protections**: 38 CHECK, 6 unique, 1 column); `store_climate_upload` and the `POST /api/integration/climate-data` endpoint;
the type selector and type column in Integration Access; a note under Recent Ingestion Batches; 16 new tests (`test_integration_ingest.py`). The suite should collect **298** cases.
The system now has 14 tables and 63 endpoints (62 under /api plus the health check).

**Verification here.** The scope checks of the real code were run against stand-in modules (8 of 8: each type refused for the other's job, the label follows the key, a corrupt scope is refused);
the static parity tests pass (5 of 5); the migration chain has one head; the extraction of the upload steps matches the original line by line; the type check shows only the usual stand-in noise.
**Not verified:** the 16 new tests, migration `d7f1a3c5e824` on PostgreSQL, the Docker build, the screens, and a real TMA or PMO delivery (none exists).


## Seventy-fourth item - the reasons for rejected rows were never returned (found trying stage 4 by hand, 7 October 2026)

**Verification run of the owner (7 October 2026).** Development stack: **298 collected, 296 passed, 2 skipped, 0 failed** (162 s); production started with `prod_up`; a TMA key was created, a three-row file was sent
(`source API_KEY_TMA`, no user as uploader, the key recorded, 3 received, 2 accepted, 1 rejected) and the same key was refused on a read endpoint (`This key is not allowed to do that`).

**Found.** That reply said one row was rejected and `errors` was an empty list. The batch object has no `errors` relationship (only `records`), so the field fell back to its default: **no reply, to a sender or to an
analyst, ever listed the rejected rows**, and `GET /climate-data/ingestions/{id}` had the same fault. The reasons were stored in `climate_ingestion_errors` all along; nothing was lost. No test looked at the field.

**Fix, with no database change.** One helper, `batch_with_errors`, builds every reply that returns a batch: the batch, a page of its rejected rows ordered by row number (500 by default) and `errors_total`. The analyst upload, the key upload and
the detail endpoint use it; the detail endpoint takes `error_offset` and `error_limit` (1 to 2000). A page and not the lot, on purpose: a file of 100,000 bad rows must not become a 100,000-item reply.
Seven new test cases in `test_climate_batch_errors.py` (key reply, manual reply, clean file, paging, the 500 cap with the true total, refused paging values). The suite should now collect **306** cases.

**Not verified.** The seven new tests and the Docker rebuild. The production stack was started before this fix; run `prod_up` again to apply it.

## Seventy-fifth item - verification run of 7 October 2026 for stages 3 and 4; report and presentation brought up to date

Run by the project owner after the keys for external systems and the rejected-row fix: development stack rebuilt without cache (249 s) and `pytest`:
**306 collected, 304 passed, 2 skipped, 0 failed** (167 s); production restarted with `prod_up` and `verify_db_constraints.py` reported **all 45 expected protections present** on the production
database, which already held data (migrations `c6e9b2d4f713` and `d7f1a3c5e824` applied without loss). Earlier the same day, by hand: a read key was created, used, refused where it must be refused and revoked; a TMA sending key delivered a three-row
file (source `API_KEY_TMA`, no user as uploader, the key recorded, 2 accepted, 1 rejected) and was refused on a read endpoint; the audit log showed every step and no key.

The report (106 pages) and the presentation (89 slides) now state: 306 test cases in 28 modules, 45 database protections (38 CHECK, 6 unique, 1 column), 14 tables, 190 columns, 19 foreign keys,
10 migrations, 63 endpoints; section 4.16 and section 5.12 (keys, with Table 5.13), the new defect in Table 5.8, the updated ER diagram and charts, and two new slides.

Still not done, and stated as such in both documents: no real sender or reader is connected to the key doors; the per-key rate limit was not exercised (the limiter is off in the tests); the QGIS and ArcGIS examples were not run;
a key sees the whole sector's approved data; there is no IP allow-list (needs the trusted-proxy setting, KG-01).


## Seventy-sixth item - the real client address behind the proxy, and an address list for each key (stage 6a; closes KG-01)

**Problem (KG-01).** In production every connection reaches the backend from the web server, so the rate limiter, which used the connection address, gave all users ONE bucket: 10 sign-in attempts a minute in total, so one person
guessing passwords could stop everyone from signing in, and the audit entries and key records held the proxy's address. An address list for keys could not be built on that.

**Fix.** `app/core/client_ip.py` (standard library only): `X-Forwarded-For` is believed only when the connection comes from a trusted proxy (`TRUSTED_PROXIES`), and only the part the proxies added: read from the right,
skipping proxies of ours; the first other address is the caller, so a prefix invented by the caller is never reached; anything unreadable falls back to the proxy, never to a guess; no setting means nothing is trusted. The
limiter's key function, the key rate-limit bucket and the audit `client_address` all use it. A mistake in the setting stops the backend at start-up. The production Compose file trusts the private networks (the web server is the only way in) and the production
checker requires the setting.

**Address list for keys.** Optional `api_clients.allowed_networks` (NULL = any address, as before) with one CHECK (`ck_api_clients_allowed_networks_not_blank`), migration `e9b3c7a1d5f2`, validated and normalised on creation (up to 20 addresses or
networks, 422 on a bad entry), checked after the key itself is proved, refused like any other bad key with the reason `address not allowed` and the address in the audit log; a list that cannot be read refuses everyone. The verification script now expects **46** protections (39 CHECK, 6 unique, 1 column).

**Found by the tests.** A list of only commas and spaces came back as an empty string instead of "no list"; the database would have refused it and the user would have seen a server error. Fixed, and covered.

**Tests.** 40 cases in `test_client_ip.py` (these were run here against the real module: 40 of 40), 19 in `test_integration_allowed_networks.py` and 3 in `test_rate_limit_real_address.py` (the limiter switched on, connecting as the proxy: one caller is stopped on the 11th
attempt while another is not; inventing addresses does not help; without a trusted proxy the header is ignored). The suite should now collect **368** cases.

**Not verified here.** The 22 tests that need the application (they have not been run), migration `e9b3c7a1d5f2` on PostgreSQL, the Docker build, and the per-caller limit on a real server (on a single Windows machine Docker's gateway hides the callers).
No report or presentation was changed, at the owner's instruction.


**First run of the owner (7 October 2026) of the 368 cases: 362 passed, 2 skipped, 2 failed, 2 errors, all four in the NEW tests, none in the product.** The three limiter tests assumed
that the installed TestClient accepts a `client=` address (it does not): they now wrap the application in a small ASGI layer that sets the connecting address, which works with any version.
One database test called its helper twice with the same user name; it now uses a second name (the part it was testing, that the database refuses a blank list, had worked). All 40 address tests
and 18 of the 19 key-list tests passed on that run. Expected after the fix: 368 collected, 366 passed, 2 skipped.

## Seventy-seventh item - verification of stage 6a and the first clean-up (stage 2): warnings, KG-04 and KG-12

**Verification run of the owner (7 October 2026) for the real client address.** Development stack, `pytest`: **368 collected, 366 passed, 2 skipped, 0 failed** (181 s), including the three rate-limit tests (one caller is stopped on the 11th
attempt while another is not; inventing addresses does not help; without a trusted proxy the header is ignored) and the 19 tests of the key address list. Production restarted with `prod_up`; `verify_db_constraints.py`: **all 46 protections present**. KG-01 is closed.

**Clean-up, three changes that do not alter what the system does:**

1. **The deprecated `datetime.utcnow()` (about 2,500 warnings on every run) is replaced by one helper**, `app/core/timeutil.py` (`utcnow()`), in the 12 files that used it, including the model defaults. It returns exactly the same naive UTC value
   (checked: within a second of the old call, no time zone), so nothing stored or compared changes. The warnings that remain come from libraries (the JWT library, passlib, reportlab), not from this code.
2. **KG-04, the misspelt audit action.** The name of a review decision was built as `SUBMISSION_` + the decision + `D`, so a rejection was written `SUBMISSION_REJECTD`. It is now `SUBMISSION_REJECTED`; an approval is unchanged. The audit log is append-only, so entries
   written earlier keep the old spelling (the Action filter will list both). Two tests in `test_review_audit_action.py` (approve and reject).
3. **KG-12, one failing dataset blanked the whole dashboard.** The seven datasets now load independently; if one fails the others are shown, and a notice names the missing ones with a "Try again" button.

**Still open and needing a decision:** KG-06, text dates are read month first. Whether the Bank's templates use day first or month first must be decided before this is changed, because changing it alters how existing text dates are understood.

**Not verified here.** The two new tests and the dashboard notice (not run); the Docker build. The suite should now collect **370** cases. No report or presentation was changed, at the owner's instruction.


## Seventy-eighth item - two-step sign-in for the Bank's staff (stage 6b, completed)

**What it is.** After the password, the BOT analyst and the System Administrator (when `MFA_REQUIRED` is on, the production default) must enter a 6-digit code from an authenticator app. Anyone who has set it up always uses it. Institution users are not asked. Development is unchanged (off by default).

**Backend (`app/core/mfa.py`, `app/api/mfa.py`).** TOTP per RFC 6238 on the standard library; the secret encrypted at rest (Fernet, key derived from `SECRET_KEY`); ten single-use recovery codes stored only as keyed hashes;
a code is accepted one 30-second step either side and each step only once (no replay); a 5-minute step token with a purpose that `get_current_user` refuses; wrong codes counted in the same lock-out as wrong passwords and rate-limited;
the administrator can reset someone else's (never their own; sessions ended, person notified, audited) and `scripts/reset_mfa.py` does it from the server; new column set on `users` and one CHECK (`ck_users_mfa_enabled_has_secret`), migration `f3a7c1e5b829`.
The verification script now expects **47** protections. The enrolment answer carries the address as a **QR picture** (a small SVG drawn with the reportlab library already in the application), and as the typed key; the picture is optional and its absence never blocks set-up.

**Frontend (new).** The sign-in page now has up to two steps (`components/TwoStepSignIn.tsx`): the code (or a recovery code), and first-time set-up with the QR, the typed key, the first code and the recovery codes shown once (the session is held back until the person confirms they saved them).
`AuthContext` handles the three kinds of answer; `api/client.ts` no longer treats a wrong code (401) as an expired session and sends the person back to the start; the administrator's Users table shows who has it on and has a **Reset two-step** button. **Without this change the production sign-in would have broken:** the old page assumed every sign-in returns tokens.

**Verified here (this environment has no database).** The code algorithm and the other building blocks: 30 of 30 tests of `test_mfa_core.py` with the real HMAC and Fernet libraries (the JWT tests used a minimal stand-in for the JWT library); the two QR tests that need no database; the QR picture decoded with QR readers
(exact address recovered from 300 of 300 drawn pictures by one reader, 298 of 300 by another; the classic OpenCV reader missed 6 of 300, and every code it missed was read by the other readers, so those are the reader's limits); the migration chain (12, one head); the schema-parity tests (5 of 5);
the type check of the frontend (only the same environment noise as before; a deliberate mistake is caught).

**Not verified here.** The 30 sign-in, enrolment, lock-out and reset tests and the 3 QR tests that use the database (`test_mfa_login.py`, `test_mfa_qr.py`) have not been run; migration `f3a7c1e5b829` on PostgreSQL; the Docker build; and the screens in a real browser
with a real authenticator app on a real phone. The suite should now collect **425** cases. No report or presentation was changed, at the owner's instruction.


## Seventy-ninth item - monitoring and alerts (stage 7)

**Verification of the previous stage (owner's run, 7 October 2026).** Development stack: **425 collected, 423 passed, 2 skipped, 0 failed** (164 s, 368 warnings, down from 2,544), including the 30 sign-in, enrolment, lock-out and reset tests and the 3 QR tests of the two-step sign-in.

**What it is.** Nine checks (`app/services/monitoring_service.py`): database response, schema version against the application's, backups, disk space, failed sign-ins in the last hour (wrong passwords and wrong codes; several accounts locked), refused API keys, accounts locked now,
API keys expiring or recently expired, and the number of active administrators. Each is a function with its inputs spelled out; one that fails is reported as "could not be checked" and never breaks the page. Results appear on **Administration, System Status** (System Administrator only, no stored secret shown),
as in-application notifications for every active System Administrator (an urgent alert repeated after a day, an attention one after a week, a change of severity at once), and as an exit code (`prod_ops.py check`, 0 / 1 / 2).
A background monitor (`monitor_loop.py`, a FastAPI lifespan task) runs the checks and the notifications every `MONITOR_INTERVAL_MINUTES` (10 in production, 0 and therefore off in development and the tests).

**Backups reach the application safely.** The backup task writes `backups/status/last_backup.json` (atomically, one small file); only that folder is mounted into the backend, read-only, so the backend can see that a backup did not happen but cannot read or change the backups. The production checker requires the setting and the read-only mount (tested: it refuses a missing mount and a writable one).

**Found by the tests.** The first version of the checker's mount rule was satisfied by an unrelated line of the same file; tightened to require the read-only mount itself. A test for "exactly 26 hours old" failed because the clock had microseconds the backup stamp does not; the test was corrected.

**Verified here (no database in this environment).** The 26 cases that need no database were run against the real code with minimal stand-ins for the missing libraries: backup levels and edges, disk levels, the overall state and the exit code, and the background monitor (starts, repeats, survives a failed run, stops cleanly, off by default); the host's status file and the application's reader agree for the three states
(copied, copy failed, no copy). The frontend type check (no new diagnostic; a deliberate mistake is caught); the schema-parity tests (5 of 5).

**Not verified here.** The 25 tests that use the database (the checks over audit rows, keys, locked accounts and administrators; the endpoint's access rules; the notifications and their de-duplication), the Docker build, and the page in a browser. The suite should now collect **476** cases. No report or presentation was changed, at the owner's instruction.


## Eightieth item - a staging environment (stage 8)

**Verification of the previous stage (owner's run, 7 October 2026).** Development stack: **484 collected, 482 passed, 2 skipped, 0 failed** (213 s), including the 25 monitoring tests that use the database. Production restarted with `prod_up`; a backup was taken (the status file was written and read);
`prod_ops.py check` answered **WARN (exit code 1)** with exactly the two real alerts: no off-machine copy of the backup (one disk) and a single administrator; the other seven checks OK; `verify_db_constraints.py`: **all 47 protections present**.

**What it is.** A second copy of the production setup on the same machine, for rehearsing upgrades and for load tests. The same code and the same `docker-compose.prod.yml`, run as project `cdr-staging` (so its containers, network and data volumes are separate), with its own environment file (`.env.staging`, its own random passwords and `SECRET_KEY`),
its own certificate folder (`certs-staging`, with a throw-away self-signed certificate made by `prod_setup.py --stack staging` using OpenSSL or Docker), ports 8080 and 8443 bound to `127.0.0.1` only, backup monitoring off (it has no backup task) and two-step sign-in off by default (so that a load test can sign in).
`staging_up.ps1` and `staging_up.sh` were generated from the production scripts by substitution, and every line that differs was reviewed; the production scripts were not changed in behaviour. A rule is written down: **no real data in staging** without the Bank's written decision.

**Changes to shared files.** The Compose file takes the folder of the backup status from `BACKUP_STATUS_HOST_DIR` and has `BACKUP_MONITORING` (defaults keep production exactly as it was); the configuration checker also requires `.env.staging` and `certs-staging/` in `.gitignore`; `prod_setup.py` has `--stack` (the production path is unchanged: it still refuses without `--domain`, writes the same file).

**Verified here (no Docker in this environment).** Creating the staging environment in a temporary copy: the file, the different secrets, the localhost-only ports, the certificate (OpenSSL: subject, 30 days, names `localhost` and `127.0.0.1`), the checker passing for staging, refusing to overwrite; the production setup in another temporary copy unchanged; every difference between the two start-up scripts listed and intended.

**Not verified here.** Starting the staging stack with Docker (the two stacks side by side, the ports, the volumes), and the new monitoring test (`test_backups_can_be_left_out_of_the_monitoring...`, which uses the database). The suite should now collect **485** cases. No report or presentation was changed, at the owner's instruction.


## Eighty-first item - load testing on staging (stage 9)

**Verification of the previous stage (owner's run, 7 to 8 October 2026).** Staging started with Docker: its own network (`cdr-staging_default`) and data volumes (`cdr-staging_cdr_prod_postgres_data`, `cdr-staging_cdr_prod_uploads`), role `cdr_app` created in its new database, three containers healthy, ports `127.0.0.1:8080` and `127.0.0.1:8443` only,
beside the production and development stacks; the staging administrator was created; `verify_db_constraints.py` on staging: **all 47 protections present**. Also seen: an unrelated container named `cdr_backend` restarting in a loop (not part of any current stack; to be inspected and, if a leftover, removed).

**What it is.** `backend/scripts/load_test.py` (standard library only), run inside the staging backend container and going through the staging web server. `setup` creates synthetic institutions, one user each and an analyst; `run` signs everybody in at once, has every institution upload a file of synthetic loans, has the analyst approve them,
then has several people read the dashboards at once for a time, and optionally uploads one very large file; it prints requests, errors, requests per second and p50, p95, p99 and maximum times, compares them with **proposed** targets (to be agreed with the Bank) and exits with 3 if one is missed or if the generated files were judged invalid.

**Three safeguards against production.** The tool refuses to run unless `CDR_ALLOW_LOAD_TEST=yes` (set by `.env.staging` only); the production checker refuses a `.env.production` that contains that variable or switches the rate limit off (tested with `false`, `False`, `0`, `no`, `OFF`; `true` and absence pass); the command addresses the staging project. The rate limit became a setting
(`RATE_LIMIT_ENABLED`, default true; staging sets it false because otherwise a load test measures the limit); a warning is logged whenever it is off.

**Verified here (no Docker).** The tool end to end against a stand-in server that checked every token and opened every uploaded workbook: the official header, row counts, unique loan numbers, real region and district pairs, outstanding principal not above the loan, interest rate 0 to 100, two reporting periods; the credentials file mode 0600; the results file.
Failure paths: refusal outside staging (no variable, and a wrong value), staging not up (a clear message, not a traceback), files judged invalid (exit 3 even though the requests succeeded), server errors (counted, sampled, exit 3). 21 unit cases of `test_load_test_tool.py` run (the guard, percentile and summary, passwords against the policy, the generated loans, the workbook, the multipart body).

**Not verified here.** That the REAL upload endpoint accepts a generated file as valid (`test_the_real_upload_accepts_a_generated_file_as_valid`, which uses the database), the real timings (this environment cannot run staging), and the tool inside the container. The suite should now collect **507** cases. No report or presentation was changed, at the owner's instruction.


## Eighty-second item - first load-test results, and what they changed (stage 9, continued)

**Verification of the previous stage (owner's runs, 8 October 2026).** Development stack: **507 collected, 505 passed, 2 skipped, 0 failed** (215 s, 373 warnings), including the test that the REAL upload endpoint accepts a generated file as valid (so the load-test data is sound).
Staging restarted with the two new settings; `load_test.py setup` created 8 synthetic institutions, one user each and an analyst; `run` met all four proposed targets.

**Measured (staging, synthetic data, the developer's machine, which production and staging share).** 20 readers, 56 requests a second: p95 391 ms, 0 errors; sign-in (9 at once): p95 0.5 s; approving: p95 0.8 s; **8 institutions uploading 2,000 loans each at once: every upload took about 16 s**;
8 uploading 500 loans each: about 5.2 s; **one file of 100,000 loans (the largest allowed): accepted, 95.7 s, no error**.

**Findings.** (1) Files are checked one after another (one backend process, processor-bound): about 1,000 loans a second in total, so the wait grows with the number of simultaneous uploads and with file size. (2) The largest file took 96 s against a 120 s web-server limit, an uncomfortable margin: on a slower machine the person would see a
time-out although the server finished, and uploading again would store a second version. (3) **A defect in the load-test tool itself**: it reported a general upload judged invalid but not a large one; found by reading the results, fixed, and tested (a large file judged invalid now fails the run, exit code 3).

**Changes.** The three endpoints that read a whole file now have a 300 s time-out in `frontend/nginx.prod.conf` (the rest keep 120 s), and the production checker requires it; the start-up scripts now recreate the web server container in their last step (a changed web-server file was otherwise never read).
The tool gained: the approval of the large file and reading at that size (`read_large`), reading while it is checked (`--mixed`, `read_during_upload`), the backend container's memory (peak, now, limit) and new proposed targets.

**Verified here (no Docker).** The extended tool against the stand-in server in four situations (normal; a large file with people reading meanwhile; only the large file judged invalid; a large file alone); the memory reader (both cgroup layouts, "max", unreadable); 24 unit cases of `test_load_test_tool.py`.

**Not verified here.** The nginx time-out in a running web server (staging is the rehearsal: `staging_up` recreates the web server; check with `nginx -T`), the new measurements (`--big-rows 100000 --mixed`: reading during a large upload, reading at that size, memory), and that the 100,000-loan file ends `VALID` (the earlier run did not print its status; the tool now does). The suite should now collect **510** cases.
Open for the Bank: the real file sizes and simultaneous uploads (a deadline day); background checking of large files is the proper design if 100,000-loan files are expected, and has not been built. No report or presentation was changed, at the owner's instruction.


## Eighty-third item - the worst case measured, and a faster way to store an upload (stage 9, continued)

**Verification of the previous stage (owner's runs, 8 October 2026).** nginx in the staging web server loaded the new configuration (`nginx -T`: syntax ok, a 300 s limit for the file endpoints and 120 s for the rest). The load test with the largest file and people reading at the same time (`run --big-rows 100000 --mixed`) ran to the end with **no error**:
the file of 100,000 loans was stored as `VALID` in **210 s** (96 s when alone); people reading meanwhile saw p50 466 ms, p95 1.3 s, p99 1.8 s, slowest 4.8 s; approving the file took 11.7 s; reading the dashboards afterwards (100,000 more loans) p95 0.92 s; the backend container peaked at **2.25 GB** (the load-test tool included).
One proposed target failed: the largest file within 120 s (it took 210 s while others were reading). Under the old 120 s limit of the web server this upload would have been cut off with a time-out error; the 300 s limit made earlier is what let it finish.

**Where the time goes** (developer's machine, 100,000 loans): pandas reads the sheet about 12 s; the row checks about 14 s before this change and about 4 s after; the rest of the roughly 96 s was storing each loan as an ORM object (100,000 held in the session until the commit).

**Changes.** (1) The row checks read plain tuples instead of pandas cells: **identical output to the old code on 11,200 records and 117,396 findings** of deliberately messy files (wrong types and values, headers on rows 1, 3 and 9, blank rows, repeated loan numbers, impossible coordinates, too many rows, an empty workbook, a header-only file), and about twice as fast.
(2) Loans and findings are stored in blocks of 5,000 with bulk INSERTs (`STORE_BLOCK`), keeping the 409 answer on a conflict. (3) One log line per upload with its stages and the process's peak memory (no data in it). (4) The load-test tool reports its own peak memory so the application's share can be separated.
Tests: `test_upload_storage_blocks.py` (a partly invalid file of 23 loans stored with blocks of 1, 4, 7, 22, 23, 24 and 5000: every loan once with its own id, the same three bad rows, the same findings as the detail endpoint reports; a clean file across blocks; the log line without any loan data).

**Verified here (no database in this environment).** The validator change by the differential run above; the tool against the stand-in server; the new tests compile. **Not verified here: the bulk storage itself** (SQLAlchemy is not installed here), nor any real timing of it; the whole suite must pass, and the same worst-case run must be repeated to see the effect.
The suite should now collect **520** cases. No report or presentation was changed, at the owner's instruction.


## Eighty-fourth item - the answer to an upload carried every loan (stage 9, continued)

**Verification of the previous stage (owner's runs, 8 October 2026).** Development stack: **520 collected, 518 passed, 2 skipped, 0 failed** (221 s), including the block-boundary tests of the bulk storage (blocks of 1, 4, 7, 22, 23, 24 and 5000). On the real PostgreSQL of staging the file of 100,000 loans was stored as `VALID` with all 100,000 records, approved and read.
Alone it took **46 s** (96 s before); with 20 people reading, 156 s (210 s before); eight institutions uploading 500 loans each took 2.8 s each (5.3 s before). The new log line showed the stages: **checking 20.5 s, storing 14.8 s, commit about 0 s** (35.4 s inside the application), 8 uploads of 500 loans each 2.3 s.

**Found by reading those numbers.** The person measured 46 s against 35 s inside the application, and the application process peaked at 526 MB at the log line but 1,487 MB later. The answers to an upload and to a review (`response_model=SubmissionDetailOut`) returned the submission object, whose `records` and `errors` relationships are ALL rows and findings: for 100,000 loans the application
loaded every loan again and wrote them all into the answer (about a gigabyte and ten seconds; approving took 10 s for a one-row change; and the answer would have been tens of megabytes for a browser). The detail endpoint had been paged earlier; these two had been missed.

**Change.** `detail_page` builds the answer for the detail endpoint, the upload and the review: the first page (100 rows, 100 findings) with the totals. The institution portal uses `status`, `valid_records` and `total_records` of the upload answer and nothing of the review answer: no screen changes, and a small file's answer is identical. Tests added (`test_upload_storage_blocks.py`): a 130-loan upload answers with 100 rows, 100 findings and the totals; a 5-loan upload answers with all 5; a review of a 120-loan submission answers with one page and the total.

**Verified here.** The module compiles, the names it needs are used and imported, and the three tests compile. **Not verified here (no database in this environment):** the three new tests and the effect on time and memory, to be measured again. The suite should now collect **523** cases. Remaining cost of a large file, in order: reading the sheet with pandas (about 15 s), storing (about 15 s).
No report or presentation was changed, at the owner's instruction.


## Eighty-fifth item - the paged answer measured; dashboards slower from run to run (stage 9, continued)

**Measured on staging after the paged answer (owner's run, 8 October 2026), the largest file (100,000 loans):** alone **36 s** (96 s at the start, 46 s after bulk storage); approving it **0.23 s** (about 10 s before: the action was cheap, the answer was what loaded every loan);
memory of the backend container (peak, load-test tool included) **0.51 to 0.58 GB** (2.25 GB at the start), the application alone at most about 0.46 GB; the tool itself 117 MB (527 MB before, when it received and read the huge answer). While 20 people read, a mixed run: reading during the upload p95 2.8 s (target 3 s, passed narrowly).

**Open: the dashboards get slower from run to run.** Reading after the large file was approved, p95: 0.92 s, 1.0 s, 1.9 s (a 5 s run), 3.6 s (target 1.5 s, failed); the number of CURRENT approved loans stayed the same (each new version replaces the previous one) but the total of stored loans grows by 100,000 per run (old versions are kept on purpose).
The dashboards aggregate in the database, which is the right design. Hypotheses, not conclusions: a plan that scans the whole table of loans; statistics made stale by the bulk load (the application's role cannot ANALYZE; autovacuum does, about a minute later); competition with autovacuum or with the other stacks on the same machine.
**Tool added to find out:** `backend/scripts/db_diagnose.py`, read-only: counts (all and current approved), freshness of the planner's statistics, and the real plan and time of the two main dashboard queries, saying whether each reads the whole table or goes through an index. Its plan reader has 4 tests.

**Verified here.** The report script compiles and its plan reader classifies three sample plans correctly (the whole table; an index; neither). **Not verified here:** the report against PostgreSQL (none in this environment), and the cause. The suite should now collect **527** cases (the 523 expected from the previous package, not yet reported, plus these 4).
No report or presentation was changed, at the owner's instruction.


## Eighty-sixth item - what made the dashboards slow, measured; the summary figures made cheaper (stage 9, continued)

**Verification of the previous packages (owner's runs, 8 October 2026).** Development stack: **523 collected, 521 passed, 2 skipped, 0 failed**, including the paged answers and the block storage. On staging the largest file (100,000 loans) took **36 to 37 s** alone (96 s at the start): checking 20.8 s, storing 14.9 s, commit about 0 s; the application process peaked at **488 to 495 MB** (1,487 MB before the answer was paged); approving it 0.2 s (10 s before); the container peaked at 0.51 to 0.58 GB.

**A correction of mine.** I had said the number of current approved loans did not grow while the dashboards slowed (p95 0.92 s, 1.0 s, 1.9 s, 3.6 s). It did: the database held 736,800 loans, **212,000 of them in current approved submissions**, because every `load_test.py setup` adds institutions with their own approved large file. The slowing follows the data the dashboards add up, as an aggregate should. The plan that reads the whole table is right (29% of it is wanted), and the statistics were fresh.

**Where the time goes (`db_diagnose.py`).** The summary figures: **1,003 ms**, of which about 850 ms is the sort for `count(distinct customer_id)` (212,000 values sorted on disk: 4 MB working memory); the by-region query: 233 ms. The application also computed the summary in **three passes** over the same loans.
**Change.** One pass for the two totals; the borrowers counted from a DISTINCT list (hashable); 32 MB of working memory for that statement only (`SET LOCAL`). `db_diagnose.py` times the old and the new way on the real data side by side and checks the figures are equal. Tests (`test_kpi_borrowers.py`): a borrower with several loans counted once; a borrower shared by two banks counted once for the sector and once for each bank; a submission not approved adds nothing; no data gives zeros.
The two ways of counting were also compared on awkward values (NULL, empty, a space, a different case): equal.

**Verified here.** The module compiles; the meaning of the two counts is equal on awkward values (in SQLite's own SQL); the three new tests compile. **Not verified here (no database in this environment):** the new tests, and the speed of the new way (that is what the next `db_diagnose.py` run shows). The suite should now collect **530** cases.
The load test reads far faster than people do; its p95 at 20 readers over-states what 20 real analysts would see, but it is the right test for a deadline day and for growth. No report or presentation was changed, at the owner's instruction.


## Eighty-seventh item - the optimised summary on production, and a way back for a forgotten administrator password (stage 9, continued)

**Verification of the previous packages (owner's runs, 8 October 2026).** Development stack: **530 collected, 528 passed, 2 skipped, 0 failed**. On staging's real PostgreSQL the old and the new way of computing the summary figures were run side by side on 212,000 current loans: **908 ms against 708 ms (22% less), the same figures** (53,132,954,000,000 TZS of loans; 69,104,015,378,173 TZS of collateral; 212,000 borrowers).
Production was then updated (`prod_up.ps1`): all containers healthy; `verify_db_constraints.py` **47 of 47**; `prod_ops.py check`: database 16 to 31 ms, schema version as expected, disk 92% free, no failed sign-ins, no locked accounts; the two open warnings were the missing off-machine backup copy and the single administrator.
A second System Administrator was created from the server with `create_admin.py --allow-additional` (the script refused without it, as designed, because an active administrator already existed); `prod_ops.py check` then reported **2 System Administrators are active**.

**A gap found in use.** The owner had forgotten the password of the production administrator, and the only server-side routes were creating another administrator or resetting two-step sign-in; there was no way to set a new password from the server. Also, the sign-in answer "Incorrect username or password" is the same for a user that does not exist and for a wrong password (on purpose), and an attempt against an unknown user is not counted as a failed sign-in, which is why the check showed none while the owner saw refusals.
**Change.** `scripts/reset_password.py` (service `app/services/account_recovery.py`): hidden prompt twice, password policy enforced, stored hashed, account unlocked, failed-sign-in count cleared, every existing session ended, a new password of their own required at the next sign-in by default, the two-step sign-in untouched, audited as `PASSWORD_RESET_CLI` without the password. Guide: `docs/ACCOUNT_RECOVERY.md`.
Tests (`test_account_recovery.py`, 16 cases): the new password works and the old one does not; stored hashed; a locked account is unlocked; old refresh tokens stop working; change required by default and optional; weak passwords refused (short, no digit, no special character, empty, none) with nothing changed; unknown user refused; two-step sign-in untouched; audit entry without the password; only the named person changes.

**Verified here.** The service and script compile; the sample passwords of the tests were checked against the real password policy. **Not verified here (no database in this environment):** the new tests (the suite should now collect **546** cases) and the script itself.
No report or presentation was changed, at the owner's instruction.


## Eighty-seventh item - the penetration-test pack (stage 10)

**Verification of what came before (owner's runs, 8 October 2026).** Production runs the new code (`prod_up`): 47 of 47 database protections; System Status OK except the off-machine backup; two System Administrators are active (the second was made with `create_admin.py --allow-additional`, its password later reset with `reset_password.py`). The summary-figures change measured on real data: 908 ms before, 708 ms after, the same figures (212,000 current loans).
Operational findings made while recovering the administrators' access, none of them a defect of the sign-in code: the sign-in code (server and browser) was read and is correct; a 200 from the sign-in endpoint proved a password right while the browser still refused it, which pointed to the browser or the typing, not the server; the first-time two-step set-up screen is easily mistaken for an error; PowerShell strips double quotes from native-command arguments (use stdin or escaped quotes); the password-reset script (`reset_password.py`) was missing from the owner's copy until the package was copied again.

**Change.** `docs/PENTEST_CHECKLIST.md`: rules of engagement; how to build staging like production for security purposes (rate limiting on, two-step required, load-test switch off, test accounts and keys); what the testers should know (roles, entry points, token lifetimes, sign-in protection, database rights); **ten observations** the developers already know, each with a suggested treatment and whether it needs a decision from the Bank; **76 test cases** in ten groups (authentication and sessions, authorisation and tenant isolation, input handling, file upload, API keys, transport and headers, infrastructure, audit and monitoring, business logic, availability) each with the result the system is built to give; severity levels; reporting; what happens after.

**The ten observations (found by reading the code and the live responses; none is fixed yet).** O1 no Content-Security-Policy; O2 tokens in `localStorage` (worse together with O1); O3 some security headers sent twice (two different HSTS lifetimes); O4 password minimum is 8 characters and no common-password check; O5 exports were not found to neutralise spreadsheet formulas (a suspicion, case C7); O6 rate limits only on sign-in, two-step and integration endpoints; O7 upload type checked by extension, declared type and parsing; O8 self-signed and trial certificates; O9 one backend process (a large upload slows others); O10 partial container hardening (the application runs as uid 10001, but the container starts as root and sets no `cap_drop`, read-only file system or `no-new-privileges`).

**Verified here.** Each statement in the pack was checked against the code or a live response: token lifetimes, lock-out figures, rate limits, upload limits, database rights (SELECT, INSERT and UPDATE only; no UPDATE on `audit_logs`), the published ports (80 and 443 only), the redirect from port 80, the disabled `/docs` in production, the Dockerfile. **Not verified:** the expected results of the cases themselves (that is what the test is for), and the suspicion in O5. No code was changed. No report or presentation was changed, at the owner's instruction.


## Eighty-eighth item - three of the pen-test observations addressed (stage 10)

**Change.**
* **O5, formula injection in exports.** Text that people type (file names, review notes, names, text quoted in audit entries) reaches the CSV and Excel exports; a cell beginning with `=`, `+`, `-` or `@` is a formula to Excel and LibreOffice. `app/core/export_safety.py`: in CSV such text gets an apostrophe first (numbers, empty cells and text that is only a number, such as `-12.5` or `+255`, are untouched so other programs still read the figures); in Excel the cell is written as text, not as a formula, with the words unchanged. Applied to all four exports (combined-exposure CSV, audit-log CSV, submission-history CSV, the Excel summary). Tests `test_export_safety.py`: the helper on awkward values, then three exports with a hostile value in them, the combined-exposure CSV unchanged in shape, and the Excel workbook with no formula cell anywhere.
* **O1, no Content-Security-Policy.** nginx now sends one: own scripts only (the application has no inline script and no `eval`), inline styles allowed, fonts from Google Fonts, map tiles from OpenStreetMap, connections only to itself, no framing, no plug-ins, forms only to itself. The production checker requires the header (and was first found too weak: it matched the word in a comment, now it matches the `add_header` command).
* **O3, doubled security headers.** nginx hides the application's four copies on the proxied paths, so each header is sent once. This also removes a contradiction: the application's HSTS said `includeSubDomains` for two years, which the nginx comment deliberately leaves to the Bank's later decision.
* **O11 (new).** The browser contacts Google Fonts and OpenStreetMap: a privacy and availability point for a central bank.
Not changed (they need the Bank's decision or a larger change): O2 (tokens in `localStorage`), O4 (password minimum 8), O6 (rate limits only on sign-in, two-step and integration), O8 (certificates), O9 (one backend process), O10 (container hardening), O11.

**Verified here.** The helper on 25 awkward values; every changed module compiles; the nginx file has balanced braces and every directive ends properly; the production checker accepts the file and refuses one without the policy and one without the header hiding. **Not verified here (no browser, no database, no nginx in this environment):** the new tests, that the policy lets every page work (the map, the fonts, the QR picture, the downloads: checked by the owner on staging, `PENTEST_CHECKLIST.md` section 3a), and that nginx accepts the file (staging start-up shows it). The suite should now collect **576** cases (541 expected from the previous package, plus 35 new in `test_export_safety.py`: 30 for the helper on awkward values, 1 for a whole row, 4 for the exports). No report or presentation was changed, at the owner's instruction.


## Eighty-ninth item - new recovery codes from the application (stage 10)

**Verification of the previous package (owner's runs, 8 October 2026).** Development stack: **581 collected, 579 passed, 2 skipped, 0 failed** (239 s), including `test_export_safety`. Staging: `nginx -t` ok; the page and the API each send **one** copy of every security header (HSTS one year without `includeSubDomains`, and the Content-Security-Policy); in the browser the staging **map and pages worked with the policy on**. Production moved with `prod_up`: same headers, System Status OK except the off-machine backup, two System Administrators active.

**The gap.** The ten recovery codes are shown only once, at set-up. A person who did not save them (it happened to the owner's own administrator account) had no way to get others: the server could make them, but nothing on screen asked it to. (The owner is protected by the second administrator and the server script, but a person alone in an institution would not be.)
**Change.** A card **Two-step sign-in: recovery codes** under the password form on the Change Password page (`components/RecoveryCodesCard.tsx`), shown only to people who use two-step sign-in and not while a temporary password must be replaced. It asks for the CURRENT 6-digit code (so a stolen session cannot do it), calls the existing server endpoint, shows the ten new codes once with Copy and Download, and says the old ones are dead; the person must tick that they saved them before it closes. **A second fix in the same change:** the browser's response handler treated a 401 from this endpoint (a wrong code) as "the session has ended" and would have signed the person out; every `/auth/mfa/` endpoint is now treated like the sign-in steps (a 401 there is only a message). No server code changed: the endpoint, its audit entry and its tests already existed (`test_mfa_login.py`).
Tests: `RecoveryCodesCard.test.tsx` (nothing is shown without two-step sign-in; the current code is sent with the spaces removed and the new codes are shown with the warning, Done disabled until saved; a wrong code shows the server's message and no codes; fewer than 6 digits cannot be sent).

**Verified here.** The four front-end files parse (TypeScript parser). **Not verified here (no React, no browser in this environment):** the type check and the build (`npm run build` runs `tsc` and is the check on staging), the new front-end tests (`npm test`), and the look of the card. No report or presentation was changed, at the owner's instruction.


## Ninetieth item - a stricter password policy (stage 10, observation O4)

**Verification of the previous package (owner's runs, 8 October 2026).** On staging `npm run build` (which runs the type check) succeeded with the new recovery-codes card; production was moved with `prod_up`. The administrator's account was recovered and recovery codes were regenerated from the application itself.

**Change.** `app/core/password_policy.py`, applied at every place a password is set (creating an account, Change Password, `create_admin.py`, `reset_password.py`): **12 characters for the Bank's staff** (BOT analysts and System Administrators), 8 for institution users, an unknown role gets 12; the letter, digit and special-character rule as before; **common passwords refused** (a well-known word with only digits or symbols added in front or behind, with look-alike characters undone: `Admin1234!`, `P@ssw0rd2026`, `Welcome@123`, `MyPassword2026!`; and passwords of four or fewer different characters); **the username may not appear in the password**. Temporary passwords are checked against the strictest rule. The password page follows the person's role (12 or 8) and explains the rule; the server names every unmet rule. Existing passwords keep working until their owner changes them. Documented in `docs/PASSWORDS.md`.
**A bug found by the table of examples before shipping.** The first version turned every digit into a letter before looking for the word, so the digits added behind it ("1234") became extra letters and hid `admin`. Fixed by cutting the added digits and symbols first, then undoing look-alikes inside the word. The table (12 acceptable and 18 refused passwords, and 3,000 generated temporary passwords) was run before and after.
**Tests.** `test_password_policy.py` gained: the minimum by role; nine good passwords accepted; fourteen common passwords refused; each unmet rule named; the username rule (and the 4-character limit); temporary passwords always acceptable; through the application: a staff account needs 12 and an institution account keeps 8, a common password is refused on creation, a staff member changing their own password meets the same rule, and a password set from the server meets the rule for that person's role. Seven existing test passwords (`Passw0rd!23`, itself a common password) were replaced.
**A language slip, corrected.** An example phrase in Swahili had been put into the page text and the code comments; it is replaced by an English example everywhere (the product is in English only). The word list keeps a few Swahili common passwords because they are real passwords people choose.

**Verified here.** The table above; every changed file compiles and the changed page parses. **Not verified here (no database, no browser, no React build):** the new and the changed tests, and the page (the staging build is the check). The suite should now collect **616** cases (581 collected in the owner's last run, plus 35 new in `test_password_policy.py`). No report or presentation was changed, at the owner's instruction.


## Ninety-first item - container hardening (stage 10, observation O10)

**Verification of the previous package (owner's runs, 8 October 2026).** Development stack: **616 collected, 614 passed, 2 skipped, 0 failed** (203 s), including the 35 new password-policy tests. Staging built and started (the front-end build with the type check passed). Production moved with `prod_up`: System Status OK except the off-machine backup; two System Administrators active; one failed sign-in in the last hour (the owner's own try).

**Change.** In `docker-compose.prod.yml` (shared by production and staging): the **backend** and the **web server** get `no-new-privileges` and `cap_drop: ALL`, keeping only what their start-up needs. Backend: `CHOWN`, `SETUID`, `SETGID` (give the uploads volume to the application's own user, then run the application as `cdr`, uid 10001). Web server: `NET_BIND_SERVICE`, `CHOWN`, `SETUID`, `SETGID`, and `DAC_OVERRIDE` (the certificate key on a Linux server is often readable only by its owner and nginx starts as root). The database container is left alone (it needs several more capabilities; a decision for the Bank). A **read-only root file system** was considered and not done: the report, chart and PDF libraries write cache files and nothing here can prove they all cope. The production checker now refuses a compose file that loses the hardening for either service (proved by removing each in turn). Documented in `DOCKER.md`; the pen-test pack (O10, case G2) updated.

**Verified here.** The compose file parses and shows the intended settings per service; the checker accepts it and refuses it with the backend's capabilities removed and with the web server's `no-new-privileges` removed. **Not verified here (no Docker in this environment): that the containers start and work with the capabilities dropped.** This is the risk of the change (a missing capability stops the start-up, for example if the image's `su` needs one that was not foreseen), so it must be tried on staging first: `staging_up` (all services must reach `healthy`), then `docker inspect` of the two containers, then a short load test (`load_test.py run --rows 200 --duration 5`) and a report download. If a service does not start, the logs name the failing call; the way back is the previous compose file (`git`/the previous package), and production is untouched until `prod_up` is run. No report or presentation was changed, at the owner's instruction.


## Ninety-second item - the container hardening tried on staging (stage 10, observation O10)

**Verified on staging (owner's run, 8 October 2026).** With the hardening in `docker-compose.prod.yml` the three services started and the backend reached `Healthy` (1.9 s); `docker inspect` of the backend shows `[no-new-privileges:true] drop=[ALL] add=[CAP_CHOWN CAP_SETGID CAP_SETUID]`, as intended. The backend therefore starts, gives the uploads volume to its own user and runs the application as the unprivileged user with only those three capabilities.

**A side effect found at once.** The load-test tool then said "Not set up yet" although `setup` had been run. Cause (read from the code): the tool keeps its saved accounts in the uploads volume when `os.access(/app/uploads, W_OK)` is true; `docker compose exec` runs as root, root no longer has `DAC_OVERRIDE` and the volume belongs to `cdr`, so the answer is no and the tool looked in `/tmp`, which is empty. The file is intact. This is the hardening working as designed, not a defect. **Remedy:** run the tool as the application's user, `exec -u cdr` (documented in `LOAD_TESTING.md` and `DOCKER.md`); the tool's message now says so when it falls back to `/tmp` although the uploads volume exists (test added). Commands that only talk to the database are not affected.

**Still to check on staging:** the web server reaching `healthy` (it started; its health check takes a little longer), the load test as `cdr`, and a PDF and an Excel report download. Production is not yet running the hardening. No report or presentation was changed, at the owner's instruction.


## Ninety-third item - rate limits per signed-in person (stage 10, observation O6)

**Verification of the previous packages (owner's runs, 8 October 2026).** The container hardening ran on staging (all three services `healthy`; `docker inspect` showed `no-new-privileges`, `drop=[ALL]`, `add=[CHOWN SETGID SETUID]`; a load test as the application's user and the PDF, Excel and CSV report downloads all worked) and was then moved to production (`prod_up`: all services `healthy`, same settings, System Status OK except the off-machine backup).

**A correction of mine.** O6 said routes other than sign-in, two-step and the integration endpoints had no rate limit. **That was wrong:** `Limiter(..., default_limits=["200/minute"])` with `SlowAPIMiddleware` limits every route; I had looked only for `@limiter.limit` decorators.
**The real weakness.** The limit was counted by ADDRESS only. Behind the Bank's network every user arrives from one address and shared one allowance of 200 a minute; a dashboard page is about ten requests, so a busy minute of twenty analysts could throttle all of them although none misbehaved. And a password-reset request (public) and the token refresh had only that general limit.
**Change.** The bucket of a request is now the signed-in person when the access token is valid (signature and expiry checked), else the real address; a forged or expired token is counted against the sender's address, so nobody can use up another person's allowance. General limit 300 a minute; password-reset request 10 and token refresh 30 a minute per address. `app/core/rate_limit.py`, `app/api/auth.py`, `app/api/password_reset.py`; documented in `docs/RATE_LIMITS.md`; the pen-test pack (O6, new cases A17 and A18) corrected.
**Tests.** `test_rate_limit_per_user.py`: two people behind one address (the 301st request of one is 429, the colleague's first is 200); the password-reset and refresh limits; which bucket a request goes into (valid token, forged token, expired token, no or malformed header).

**Verified here.** The choice of bucket was run with stand-ins for the two libraries missing in this environment (`slowapi`, `jose`): a valid token gives the person, a forged or unknown token, no header, a non-Bearer header and an empty token give the real address (including the proxy case with `X-Forwarded-For`). Everything compiles. **Not verified here (no database, no `slowapi`, no `jose`):** the new tests, that signature and expiry are checked by the real `decode_access_token`, and the behaviour through the application. The suite should now collect **629** cases (616 in the owner's last run, plus 13 new). No report or presentation was changed, at the owner's instruction.


## Ninety-fourth item - dates in uploaded files: no more silent guessing (stage 10, known gap KG-06)

**Verification of the previous packages (owner's runs, 8 October 2026).** Development stack: **630 collected, 628 passed, 2 skipped, 0 failed** (203 s), including the per-person rate-limit tests. Staging and production moved with `prod_up`: all services `healthy`.

**The gap (KG-06), and what reading the code showed.** Text dates in a loan file were read by `pd.to_datetime`, which assumes the MONTH comes first when a date is ambiguous: `04/05/2026` became 5 April although a writer in Tanzania means 4 May. The decision "day first or month first?" had been waiting for the Bank. Reading the code showed something worse that no decision would have fixed: **a number in a date column was turned into a date of 1970** (`45000` became 1970-01-01), and nothing marked the row. (An earlier comparison of old and new code had missed it because both did the same.)
**Change.** `app/services/date_rules.py`: no guess is made where the Bank has not chosen. A real date cell, year-first text, month-in-letters text and day-or-month-first text that can mean only one thing (one of the first two numbers above 12, or both equal) are accepted; an ambiguous date (both 12 or less), a number, a two-digit year, an impossible date and a year outside 1900 to 2100 are refused as a finding on the row with the reason and the way to write it ("04/05/2026 could be 4 May 2026 or 5 April 2026: write it as YYYY-MM-DD (2026-05-04 or 2026-04-05) or use a date cell"); a refused date is never stored. The rule that maturity cannot precede disbursement is unchanged. Applied to the three date columns. Documented in `docs/UPLOAD_DATES.md` (what is accepted, why, and the one place to change if the Bank later fixes a convention).
**What this does not decide.** The Bank's choice of convention is still open; the system no longer depends on it. Files that were already accepted keep their stored dates; only new uploads are read under the rules. Institutions that wrote ambiguous text dates will now see findings and must correct the file (a real date cell avoids the problem).
**Tests.** `test_date_rules.py` (47): the accepted forms, the ambiguous ones, everything refused (numbers, two-digit years, impossible days, implausible years), empty cells, the hints, and through the application a file with good and doubtful dates (the good ones stored, the doubtful ones refused with the reason and never stored, `25/03/2029` read day first because it can only be that) and the unchanged maturity rule.

**Verified here.** The rules on 35 forms; the whole upload checker on a seven-row file (ISO, ambiguous, date cell with a day-first date, a number, maturity before disbursement, month names, empty): each row came out as the table in `UPLOAD_DATES.md` says; the pure parts of the new tests. **Not verified here (no database):** the two tests through the application. The suite should now collect **677** cases (630 in the owner's last run, plus 47). No report or presentation was changed, at the owner's instruction.
