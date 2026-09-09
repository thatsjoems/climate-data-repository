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
| 9 | Advanced filtering (institution, period, geography, hazard) | **PARTIAL (MVP)** | Status filter implemented; full geography/period filtering is **Should-Have** for the next phase |
| 10 | Dashboard Export (PDF, Excel, CSV, image) | **PARTIALLY IMPLEMENTED** | `GET /api/reports/summary.pdf` (BOT_USER only) automatically compiles the KPI summary, hazard exposure, combined climate-financial exposure, and recent Risk Advisory Reports into a formatted PDF using `reportlab` - directly implementing BOT's recommendation to "automate the system for generating their reports." Excel/CSV/image export are not yet built |
| 11 | Password recovery workflow | **IMPLEMENTED** | Public "Forgot Password" page (`ForgotPassword.tsx` → `POST /api/password-reset-requests`) creates a reset request without revealing whether the account exists; a SYSTEM_ADMIN reviews and approves/rejects it, generating a new temporary password shared out-of-band |
| 12 | Integration with RTIS, BSIS, QGIS, ArcGIS | **NOT YET IMPLEMENTED - Out of scope (Future/Mock)** | No real credentials/API access were provided. Backend design (modular API routers) is "integration-ready" but no real adapter has been built. **Note:** the Geospatial Overview map itself was built independently of these systems — see item 12b and `docs/GEOSPATIAL_MAP.md` |
| 12b | Geospatial visualization of climate/financial exposure | **IMPLEMENTED (region-level)** | `GET /api/analytics/map-points` + `HazardMap.tsx` render an interactive map (Leaflet + OpenStreetMap - free, self-hosted, no external GIS dependency) plotting real hazard-exposure figures at real region-centroid coordinates. Deliberately self-sufficient per explicit direction: the system should operate on institution-submitted + own climate data alone, not depend on an external map service. Precise per-loan coordinates await BOT's forthcoming data template (see `docs/GEOSPATIAL_MAP.md`) |
| 13 | Institutional onboarding (focal person nomination) | **REMOVED per BOT operational preference** | A public self-service "Request Access" form was originally built (a prospective institution submits details, SYSTEM_ADMIN approves), but was subsequently removed entirely at BOT's explicit instruction. Onboarding is now purely Admin-driven: a SYSTEM_ADMIN creates the Institution and User directly via the Administration page - no public request/approval step exists anymore |
| 14 | Audit logging | **IMPLEMENTED** | `AuditLog` model + `audit_service.py`, records LOGIN, SUBMISSION_CREATED, USER_CREATED, etc. |
| 15 | Climate risk assessment for the banking sector (exposure analysis and supervisory reporting) | **IMPLEMENTED** | Descriptive exposure-by-region/hazard data (`analytics_service.get_hazard_exposure()`) feeds a dedicated **Risk Advisory Reports** module (`risk_advisories.py`, `RiskAdvisoryNote` model), where the BOT Analyst authors climate-risk assessments and recommendations for internal decision-making, grounded in a real, queried data snapshot captured at the time of writing. Consistent with the "no fabricated risk score" rule: the system never computes or infers the risk level itself — that judgement is always the analyst's own, attributed and timestamped |
| 16 | **Core project AIM**: combine financial sector data with climate/meteorological data | **IMPLEMENTED** | `analytics_service.get_combined_climate_financial_exposure()` (`GET /api/analytics/combined-climate-financial-exposure`) joins real `ClimateRecord` readings (rainfall, temperature, hazard) with real `SubmissionRecord` loan/collateral exposure for the same region and reporting period. Previously these two datasets existed in isolation (climate_hazard_exposure was only self-reported by institutions); this view is the first place the two are actually queried together |
| 16 | Meteorological data integration (TMA) | **SAMPLE/SYNTHETIC** | `ClimateRecord` table is populated with SAMPLE (synthetic) data tagged `source="SYNTHETIC_SAMPLE"` - NOT real TMA data |
| 17 | Climate Vulnerability Maps (PMO) | **NOT YET IMPLEMENTED** | No data or access was provided - out of scope for this prototype |

## Summary

**See `docs/SECURITY_HARDENING.md`** for a detailed record of a subsequent
security/data-integrity hardening pass: multi-tenant analytics isolation,
duplicate/superseded-submission handling, invalid-can't-be-approved and
maker-checker workflow rules, upload limits, district-region validation,
brute-force login protection, forced password change on temporary
credentials, reduced institution info disclosure, and a paginated audit log
viewer. That document also lists what was deliberately left out as outside
the ICN's scope (e.g. database migrations, JWT/cookie rearchitecture).

**A further role-separation refinement** was then applied on top of that:
SYSTEM_ADMIN's dashboard is now strictly administration-only (users,
institutions, access requests, password resets, audit log) with zero
visibility into climate data, submissions, or analytics; BOT_USER (the
Analyst) is conversely the only internal role with access to any data/climate
content, and has no visibility into administration matters (audit log, user
list, access/password-reset requests). Institution users additionally gained
the ability to review the actual rows they submitted (not just validation
errors) and re-download their original uploaded file. See
`docs/ROLE_SEPARATION.md` for the full before/after permission matrix.


- The entire **MUST HAVE** workflow (login \u2192 template \u2192 upload \u2192 validation \u2192 storage \u2192 internal review \u2192 dashboard) has been **built and fully functional**.
- **SHOULD HAVE** items (export, advanced filters, password recovery) - the underlying foundation exists (APIs already return correct data), but the additional UI/endpoints have not yet been added.
- **FUTURE WORK** (live RTIS/BSIS/QGIS/ArcGIS integration, real TMA/PMO data) - not possible without real access/credentials from BOT - these are clearly documented as gaps, not hidden.
