# Security & Data-Integrity Hardening — Implementation Report

This document records a hardening pass requested against a generic 27-point
production-readiness checklist. Per explicit instruction, **only items
genuinely grounded in the ICN Concept Note were implemented**; items that
would take this training prototype into enterprise/production territory not
required by the ICN were deliberately left out, and are listed at the bottom
with the reasoning.

## Files changed

**Backend:** `app/models/models.py`, `app/core/config.py`, `app/core/password_policy.py`,
`app/main.py`, `app/api/auth.py`, `app/api/users.py`, `app/api/institutions.py`,
`app/api/audit.py`, `app/api/access_requests.py`, `app/api/password_reset.py`,
`app/api/submissions.py`, `app/api/analytics.py`, `app/services/analytics_service.py`,
`app/services/validation_service.py`, `app/services/template_generator.py`,
`app/schemas/schemas.py`, `requirements.txt`, `pytest.ini`, `tests/*` (new).

**Frontend:** `src/components/ProtectedRoute.tsx`, `src/context/AuthContext.tsx`,
`src/pages/ChangePassword.tsx`, `src/pages/InstitutionPortal.tsx`,
`src/pages/InternalPortal.tsx`, `src/pages/AdminPanel.tsx`, `src/index.css`.
Three unused leftover files (`Sidebar.tsx`, `Topbar.tsx`, `DashboardLayout.tsx`
from an earlier abandoned layout attempt, never imported anywhere) were deleted.

## 1. Multi-tenant data isolation (Critical)

**Real gap found and fixed.** `GET /api/analytics/*` endpoints (`kpi-summary`,
`hazard-exposure`, `combined-climate-financial-exposure`) previously had **no**
institution scoping — an `INSTITUTION_USER` could see sector-wide totals across
every institution. `submissions.py` already isolated correctly; analytics did not.

Fix: `analytics_service.py` functions now accept an `institution_id` parameter;
`analytics.py`'s `_scope_for()` derives it **only** from the authenticated
user's own `institution_id` (never from a query parameter or request body) and
passes `None` (sector-wide) for `SYSTEM_ADMIN`/`BOT_USER`. Covered by
`tests/test_rbac_and_isolation.py`.

`GET /api/institutions` also now returns a reduced shape
(`InstitutionPublicOut`: id/code/name/type only, no contact email/phone) to
`INSTITUTION_USER`, since other institutions' contact details are not that
user's business (least privilege).

## 2. Double-counting / submission versioning

**Real gap found and fixed**, scoped down from the full event-sourced version
history originally requested. A `SUPERSEDED` status was added to
`SubmissionStatus`. Uploading a new submission for the same
institution + `reporting_period` automatically marks every earlier
still-active submission for that pair as `SUPERSEDED`
(`app/api/submissions.py`). Analytics (`_active_records_query` in
`analytics_service.py`) exclude `REJECTED` and `SUPERSEDED` submissions, so
only the latest attempt per institution+period ever contributes to totals.
Covered by `test_new_upload_supersedes_previous_submission_same_period`.

*Not built:* a full audit trail of every historical version, or an
`original_submission_id` lineage chain — the ICN does not ask for this level
of version history, and it would be materially over-engineering.

## 3. Submission workflow rules

- `INVALID` submissions can no longer be `APPROVE`d (only `REJECT`ed or
  corrected via a fresh upload) — enforced server-side in `review_submission`.
- Maker-checker: a reviewer can never approve/reject a submission they
  uploaded themselves (relevant when `SYSTEM_ADMIN` uploads for testing/support).
- `APPROVED`/`REJECTED`/`SUPERSEDED` submissions can't be reviewed again.

## 4. Secure file upload

`MAX_UPLOAD_SIZE_MB` (default 20) and `MAX_UPLOAD_ROWS` (default 100,000),
both configurable via `.env`. Oversized files are rejected before parsing;
oversized row counts are rejected after a cheap read. Filenames are never
trusted for the storage path (always a generated UUID). Corrupt/malformed
files are caught and returned as a normal 400 error instead of a 500 crash.

## 5–7. Strong data validation

- `district` must belong to the selected `region`, checked against the
  verified 31-region/193-district reference table in `template_generator.py`
  (sourced from Wikipedia's "Districts of Tanzania", not invented).
- Cross-submission duplicate `loan_id` detection (institution + reporting_period + loan_id),
  not just within a single file.
- The reporting period typed into the upload form must match the
  `reporting_period` column inside the file for every row — a mismatch
  rejects the whole submission with a specific explanation, rather than
  silently keeping ambiguous data.

*Not built:* a full separate "master data" admin UI for managing reference
lists (regions/hazards are still constants in code) — reasonable for this
scale of prototype; revisit if the list needs to change without a redeploy.

## 8–11. Authentication & secret hardening

- Login now locks an account for `LOGIN_LOCKOUT_MINUTES` (default 15) after
  `MAX_FAILED_LOGIN_ATTEMPTS` (default 5) wrong passwords.
- A non-existent username and a wrong password return the **identical**
  error, preventing username enumeration.
- All temporary/admin-issued passwords (access-request approval, password-reset
  approval, admin-created users) now use `secrets.choice` (cryptographically
  secure) via `generate_secure_temp_password()`, replacing the previous
  `random.choice` usage.
- Every admin-issued password now sets `must_change_password = True`; the
  frontend (`ProtectedRoute`) forces the user to `/change-password` before
  they can reach anything else, and the flag clears automatically once they
  set their own password.
- The app refuses to start if `ENVIRONMENT=production` and `SECRET_KEY` is
  still the default `"change-me"` (`main.py`).

*Not built (see "Deliberately out of scope" below):* moving the JWT out of
`localStorage` into HttpOnly cookies with CSRF protection, and a refresh-token
architecture. This is a legitimate hardening idea in general, but is a large
architectural change the ICN never asks for, and is explicitly the kind of
"production security certification" item already documented as future work.

## 12–13. Migrations & centralized RBAC

*Deliberately skipped* — see bottom.
RBAC was reviewed endpoint-by-endpoint as part of fixing item 1; no separate
policy-engine abstraction was introduced, since the existing
`require_roles(...)` dependency pattern is already centralized enough for
this codebase's size and was already used consistently everywhere except the
analytics gap that's now fixed.

## 14. Institution information disclosure

Covered under item 1 above (`InstitutionPublicOut`).

## 15. Audit log hardening

`GET /api/audit-logs` previously hard-capped at the first 500 records with no
way to page or filter. It's now paginated (`limit`/`offset`, default page
size 25 in the UI) and filterable by `action`, `entity_type`, `user_id`, and
a date range. **A UI for viewing the audit log did not exist at all before
this pass** — the backend endpoint was built but never surfaced — this is now
added to the Admin Panel with a "Load More" pattern and an action filter.

## 16–19. Climate data model, event linkage, geospatial columns, risk-modeling wording

*Deliberately skipped* — see bottom. The existing `source` field
(`SYNTHETIC_SAMPLE` vs a real source) already honestly distinguishes demo
data, and the Risk Advisory Reports module (built in an earlier session) was
already careful to never let the system compute a risk level — a re-check
confirms this remains true; no wording changes were needed.

## 20. Analytics correctness

Directly resolved by items 1 and 2 (institution scoping + excluding
rejected/superseded submissions from every aggregate).

## 21. Automated testing

Added `backend/tests/` (pytest): `test_auth.py`, `test_rbac_and_isolation.py`,
`test_upload_and_workflow.py`, `test_password_policy.py`, plus `conftest.py`
providing an isolated in-memory SQLite database per test (never the real
`cdr.db`). Covers login/lockout, RBAC denial, cross-institution isolation
(the critical acceptance criterion), upload validation rules, the
invalid-can't-be-approved and maker-checker rules, superseding, and password
policy enforcement.

**Honesty note:** these tests were written and syntax-checked
(`python -m py_compile` / `ast.parse` on every file) but **could not actually
be executed** in this environment (no internet access to install
`fastapi`/`httpx`/`pytest`). Run `pip install -r requirements.txt && pytest`
yourself and treat this as unverified until you've seen it pass.

## 22. Production observability

Only the health check was improved — `GET /api/health` now actually executes
`SELECT 1` against the database and reports `"degraded"` if that fails,
instead of unconditionally returning `"ok"`. Structured logging, correlation
IDs, and metrics infrastructure were *not* added — see bottom.

## 23–25. Docker/API/frontend hardening

*Deliberately skipped* — see bottom.

## 26. Documentation

This file. Also see the updated
`docs/ICN_REQUIREMENTS_TRACEABILITY_MATRIX.md` and
`docs/ASSUMPTIONS_AND_LIMITATIONS.md`.

---

## Deliberately left OUT of scope (not grounded in the ICN)

| Item | Why it was skipped |
|---|---|
| Alembic database migrations | ICN never mentions migrations; `Base.metadata.create_all()` was already an accepted, documented simplification for this training prototype |
| JWT → HttpOnly cookie + CSRF rearchitecture, refresh tokens | Large architectural change with no ICN basis; "secure login" is already met by hashing, lockout, and enumeration protection above |
| Climate-event geospatial data model (event ID, polygons, confidence) | Would require inventing structure for data we don't have access to (no real TMA/PMO feed) — explicitly against this project's no-fabrication rule |
| ~~Latitude/longitude columns~~ | **Superseded** — see `docs/GEOSPATIAL_MAP.md`: a region-level map was built using known region centroid coordinates and real hazard-exposure data, without waiting for per-loan coordinates |
| Full structured logging / correlation IDs / metrics pipeline | Production observability tooling, not an ICN requirement |
| Docker non-root user, resource limits, secret vaults | ICN never mentions Docker (it was an earlier optional addition, not an ICN requirement) |
| Broad API rate limiting (beyond login) | Disproportionate for an 8-week prototype; login-specific brute-force lockout addresses the concrete risk |

## Commands to verify (run yourself)

```bash
cd backend
pip install -r requirements.txt
pytest -v
```

## Follow-up fixes (after the 30-point audit pass)

Three additional gaps identified during that audit were fixed:

1. **docker-compose.yml no longer hardcodes `postgres/postgres`** - credentials
   and `SECRET_KEY` are now read from environment variables (with dev-only
   fallbacks), overridable via a `.env` file (see `.env.docker.example`).
2. **Database indexes added** on `Submission.institution_id`,
   `Submission.reporting_period`, `Submission.status`,
   `SubmissionRecord.region`, `SubmissionRecord.loan_id`,
   `ClimateRecord.region`, `ClimateRecord.source`,
   `ClimateRecord.observation_date`, `ClimateRecord.reporting_period`,
   `ClimateRecord.station_id` - the columns most queried by institution,
   period, region, and status filters throughout analytics and submissions.
3. **Upload hardening**: content-type is now checked in addition to file
   extension, and a file that fails validation is deleted from disk instead
   of being left behind as orphaned debris.

Still deliberately not done (unchanged from the reasoning above): Alembic
migrations, cookie/CSRF session rearchitecture, rate limiting beyond login,
and a structured application-logging framework beyond the existing audit
log - all remain disproportionate for this training prototype's scope.
