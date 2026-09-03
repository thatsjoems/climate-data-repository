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
| 10 | Dashboard Export (PDF, Excel, CSV, image) | **NOT YET IMPLEMENTED (Future Work)** | Data structure already exists (APIs return JSON) - export endpoints are the next straightforward addition |
| 11 | Password recovery workflow | **IMPLEMENTED** | Public "Forgot Password" page (`ForgotPassword.tsx` → `POST /api/password-reset-requests`) creates a reset request without revealing whether the account exists; a SYSTEM_ADMIN reviews and approves/rejects it, generating a new temporary password shared out-of-band (same pattern as access requests, since no SMTP integration is available) |
| 12 | Integration with RTIS, BSIS, QGIS, ArcGIS | **NOT YET IMPLEMENTED - Out of scope (Future/Mock)** | No real credentials/API access were provided. Backend design (modular API routers) is "integration-ready" but no real adapter has been built |
| 13 | Institutional onboarding (focal person nomination) | **IMPLEMENTED** | Public "Request Access" form (`RequestAccess.tsx` → `POST /api/access-requests`) lets a prospective institution submit its details without self-registering; a SYSTEM_ADMIN reviews and approves/rejects the request, which is the only point at which an Institution + User account are created |
| 14 | Audit logging | **IMPLEMENTED** | `AuditLog` model + `audit_service.py`, records LOGIN, SUBMISSION_CREATED, USER_CREATED, etc. |
| 15 | Climate risk assessment for the banking sector (exposure analysis and supervisory reporting) | **IMPLEMENTED** | Descriptive exposure-by-region/hazard data (`analytics_service.get_hazard_exposure()`) feeds a dedicated **Risk Advisory Reports** module (`risk_advisories.py`, `RiskAdvisoryNote` model), where the BOT Analyst authors climate-risk assessments and recommendations for internal decision-making, grounded in a real, queried data snapshot captured at the time of writing. Consistent with the "no fabricated risk score" rule: the system never computes or infers the risk level itself — that judgement is always the analyst's own, attributed and timestamped |
| 16 | Meteorological data integration (TMA) | **SAMPLE/SYNTHETIC** | `ClimateRecord` table is populated with SAMPLE (synthetic) data tagged `source="SYNTHETIC_SAMPLE"` - NOT real TMA data |
| 17 | Climate Vulnerability Maps (PMO) | **NOT YET IMPLEMENTED** | No data or access was provided - out of scope for this prototype |

## Summary

- The entire **MUST HAVE** workflow (login \u2192 template \u2192 upload \u2192 validation \u2192 storage \u2192 internal review \u2192 dashboard) has been **built and fully functional**.
- **SHOULD HAVE** items (export, advanced filters, password recovery) - the underlying foundation exists (APIs already return correct data), but the additional UI/endpoints have not yet been added.
- **FUTURE WORK** (live RTIS/BSIS/QGIS/ArcGIS integration, real TMA/PMO data) - not possible without real access/credentials from BOT - these are clearly documented as gaps, not hidden.
