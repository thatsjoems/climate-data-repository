# Role Separation: Administration vs. Data Analysis

This document records a deliberate architectural refinement: **SYSTEM_ADMIN**
and **BOT_USER (Analyst)** now have entirely non-overlapping areas of the
system, reflecting two genuinely different jobs:

- **SYSTEM_ADMIN** = identity & access management ("who is allowed in").
- **BOT_USER** = climate/financial data review and risk analysis ("what does
  the data say").

Previously these two roles shared a single Internal Dashboard and had
significant permission overlap. That overlap has been removed.

## Permission matrix (current)

| Area | INSTITUTION_USER | BOT_USER (Analyst) | SYSTEM_ADMIN |
|---|---|---|---|
| Own institution's dashboard (KPIs, upload, history) | ✅ | — | — |
| Download own submitted template/file | ✅ | — | — |
| **Review own submitted records** (not just errors) | ✅ | — | — |
| Upload data | ✅ | ❌ | ❌ |
| List / view submissions | own institution only | ✅ (all) | ❌ |
| Download a submission's original file | own institution only | ✅ (all) | ❌ |
| Approve / reject a submission | ❌ | ✅ | ❌ |
| KPI summary / hazard exposure / combined climate-financial exposure / climate trends | own institution scope | ✅ (sector-wide) | ❌ |
| Risk Advisory Reports (read) | ❌ | ✅ | ❌ |
| Risk Advisory Reports (author) | ❌ | ✅ | ❌ |
| Manage institutions (create/deactivate) | ❌ | ❌ | ✅ |
| Manage users (create/activate/deactivate) | ❌ | ❌ | ✅ |
| View user list | ❌ | ❌ | ✅ |
| Approve/reject Password Reset Requests | ❌ | ❌ | ✅ |
| Generate automated PDF summary report | ❌ | ✅ | ❌ |
| Audit log (login activity, account/institution changes) | ❌ | ❌ | ✅ |
| Change own password / forced password change | ✅ | ✅ | ✅ |

## Notification routing (who gets notified about what)

| Event | Goes to |
|---|---|
| Submission uploaded / superseded | BOT_USER only |
| Submission approved/rejected | the submitting institution user only |
| Password reset requested/approved/rejected | SYSTEM_ADMIN only |
| Institution created/deactivated | SYSTEM_ADMIN only |
| User account created/activated/deactivated | the affected user (+ SYSTEM_ADMIN peers for deactivation) |
| Risk Advisory published | other BOT_USER analysts only |

## What changed to get here

- `GET /api/analytics/*` (kpi-summary, hazard-exposure,
  combined-climate-financial-exposure, climate-trends): now
  `require_roles(INSTITUTION_USER, BOT_USER)` - SYSTEM_ADMIN removed.
- `GET/POST /api/risk-advisories*`: now `require_roles(BOT_USER)` only for
  both reading and authoring - SYSTEM_ADMIN removed entirely (previously could read).
- `POST /api/submissions/upload`, `GET /api/submissions`,
  `GET /api/submissions/{id}`: now `require_roles(INSTITUTION_USER, BOT_USER)`
  (upload is INSTITUTION_USER-only) - SYSTEM_ADMIN removed from all three.
- `GET /api/audit-logs`: now `require_roles(SYSTEM_ADMIN)` only - BOT_USER removed.
- `GET /api/users`: now `require_roles(SYSTEM_ADMIN)` only - BOT_USER removed.
  (BOT_USER no longer needs this: Risk Advisory author names are now returned
  directly as `created_by_name` in the API response instead of requiring a
  separate user-list lookup.)
- All `notify_roles([SYSTEM_ADMIN, BOT_USER], ...)` calls were split so each
  event notifies only the role it's actually relevant to (see table above).
- New: `GET /api/submissions/{id}/download` lets an institution re-download
  their own original uploaded file, and lets a BOT_USER download any
  institution's file while reviewing. Not available to SYSTEM_ADMIN.
- New: `SubmissionDetailOut` now includes `records` (the actual submitted
  rows: loan_id, borrower_name, amounts, region/district, hazard, validity) -
  previously only the validation error list was returned, so an institution
  could see what was wrong but not review the data itself.
- Frontend: `SYSTEM_ADMIN` logging in now lands directly on the Administration
  page (`/admin`) instead of the data-heavy Internal Dashboard; the
  Administration page's "Back to Dashboard" link was removed since there is
  no other dashboard for that role to go to.

## Rationale

This is the same "separation of duties" principle already used for the
maker-checker submission workflow, applied consistently at the role level:
a person managing *who has access* to the system should not also be the one
assessing *what the data says*, and vice versa. It also directly closes a
gap noted earlier in this project's own review: previously there was no
capability reserved exclusively for the Analyst that the Admin didn't also
have - Admin was a strict superset of Analyst's permissions. That is no
longer true; each role now has a genuinely distinct, non-overlapping mandate.

## Later update: Request Access removed; Automated Reports added

Per explicit direction from BOT, the public self-service "Request Access"
feature (`RequestAccess.tsx`, `POST /api/access-requests`, and the
corresponding "Pending Access Requests" section in the Administration page)
was **removed entirely**. Institutional onboarding is now purely
Admin-driven: a SYSTEM_ADMIN creates the Institution and User directly via
the existing "Add New Institution" / "Add New User" forms - there is no
public request or approval step anymore. The `AccessRequestStatus` enum and
`AccessRequestDecision` schema were kept (Password Reset Requests reuse them),
but `InstitutionAccessRequest` itself and its API/UI were deleted.

Separately, `GET /api/reports/summary.pdf` (BOT_USER only) was added,
directly implementing BOT's recommendation to "automate the system for
generating their reports" - see `docs/ICN_REQUIREMENTS_TRACEABILITY_MATRIX.md`
item 10.
