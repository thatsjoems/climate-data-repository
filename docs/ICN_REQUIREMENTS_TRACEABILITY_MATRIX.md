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
