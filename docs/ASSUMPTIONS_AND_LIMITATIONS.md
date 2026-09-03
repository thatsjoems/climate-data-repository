# Assumptions, Sample Data, and Limitations

## Data Used

| Data Type | Status | Notes |
|---|---|---|
| Loan / Collateral records | **SAMPLE only (one example row in the template)** | Real data will come from reporting institutions via upload |
| Climate records (rainfall, temperature, hazard) | **SYNTHETIC (randomly generated)** | `init_db.py` generates data for 2024-2026 across 6 regions, purely to demonstrate how analytics/dashboards will work. **NOT real TMA or PMO data** |
| Users / Institutions | **DEMO accounts** | `admin`, `bot_analyst`, `bankA_user`, `bankB_user` - change passwords before real use |

## Assumptions Made (where the ICN did not specify details)

1. Three roles were chosen: `SYSTEM_ADMIN`, `BOT_USER` (internal BOT user), `INSTITUTION_USER` (external institution). The ICN referred to "role-based access" without naming formal roles.
2. The Excel template layout (columns: loan_id, borrower_name, loan_amount_tzs, etc.) is a **technical proposal**, not an officially issued BOT data specification. A real institution will need to provide the official data layout.
3. The Approve/Reject workflow for BOT_USER is a prototype assumption - the ICN did not specify a formal approval workflow.
4. The `reporting_period` format (YYYY-Qn) is a technical decision, not an official specification from the ICN.

## Deliberately Not Built (out of scope for this 8-week prototype / no access available)

- **Live integration** with RTIS, BSIS, QGIS, ArcGIS - no real credentials/API access were available.
- **Real data** from TMA (Tanzania Meteorological Authority) and PMO (Climate Vulnerability Maps) - not available in this environment.
- Automated email delivery for approved access requests: **now supported optionally.** If SMTP
  credentials are configured in `.env` (`SMTP_HOST`, `SMTP_FROM_EMAIL`, etc.), the system emails
  generated usernames/temporary passwords automatically. If left blank — the default in this
  training environment — credentials are shown once to the approving System Admin, who relays
  them to the institution through a verified channel (phone/official email). The same applies to
  approved password reset requests (`docs/ICN_REQUIREMENTS_TRACEABILITY_MATRIX.md`, item 11).
- Dashboard export to PDF/Excel/Image (the underlying data structure exists, but export endpoints have not been added).
- Enterprise SSO, production-grade deployment, and formal security certification.

## Security - What Was Implemented in This Prototype

- All passwords are hashed (bcrypt) - never stored as plain text.
- No secret or password is hardcoded in the code - all come from `.env`.
- Role-Based Access Control (RBAC) is enforced on every sensitive endpoint.
- Data isolation: an institution user (`INSTITUTION_USER`) can only see submissions from their own institution.

**Before any production use:** this is a training prototype (EASTC 8-week
programme) - it has not undergone penetration testing, does not have production
security certification, and the demo SECRET_KEY MUST be changed.
