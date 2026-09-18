# Database Schema

CDR uses SQLAlchemy ORM models as the application-level schema definition and
Alembic as the authoritative mechanism for schema evolution. `Base.metadata`
is used by tests, but production startup does not call `create_all()`.

## Tables

| Table | Purpose |
|---|---|
| `institutions` | Reporting/supervisory institutions and controlled institution metadata |
| `users` | Authentication, roles, institution ownership and login-lockout state |
| `refresh_tokens` | Hashed, revocable refresh sessions |
| `submissions` | Uploaded financial submission/version and review state |
| `submission_records` | Individual loan/exposure rows belonging to a submission |
| `validation_errors` | Row/column validation findings for financial submissions |
| `climate_ingestion_batches` | One climate ingestion run and its aggregate outcome |
| `climate_ingestion_errors` | Row-level climate ingestion failures linked to a batch |
| `climate_records` | Climate observations, provenance and QC state |
| `risk_advisory_notes` | Append-only analyst-authored advisory records and data snapshots |
| `notifications` | User-facing workflow notifications |
| `password_reset_requests` | Admin-reviewed password reset requests |
| `audit_logs` | Append-oriented record of important system actions |

## Core relationships

```text
Institution 1 ──< User
Institution 1 ──< Submission
User 1 ──< Submission (submitted_by)
Submission 1 ──< SubmissionRecord
Submission 1 ──< ValidationError

ClimateIngestionBatch 1 ──< ClimateRecord
ClimateIngestionBatch 1 ──< ClimateIngestionError

User 1 ──< RefreshToken
User 1 ──< Notification
User 1 ──< RiskAdvisoryNote
User 1 ──< AuditLog
User 1 ──< PasswordResetRequest
```

## Climate provenance pipeline

`source file -> climate_ingestion_batches -> climate_records -> QC state -> analytics`

Newly ingested observations always receive a `batch_id`. The column remains
nullable only for legacy records created before batch provenance was introduced.

## Duplicate policy

The ingestion service rejects duplicates before insert. Database-level unique
partial indexes provide a second line of defence when a reliable source ID or
station ID exists. Observations with neither identifier remain application-
validated because a database cannot safely distinguish two legitimate unnamed
stations without inventing an identity rule.

## Financial submission identity

A loan is logically identified for duplicate checking by `institution +
reporting_period + loan_id` among active submissions. Application workflow
controls superseding/versioning; the schema deliberately does not use a simple
`UNIQUE(loan_id)` because the same loan ID may legitimately recur across periods.

## Database integrity constraints

The schema enforces non-negative financial amounts, bounded interest rates and
coordinates, valid climate months, controlled climate QC flags and controlled
period types. Application validation remains responsible for higher-order rules
such as region/district membership and reporting-period/file consistency.

## Migrations

Run:

```bash
cd backend
python -m alembic upgrade head
```

The container startup runs `init_db.py`, which applies the same migrations and
then seeds demo data only when the database is empty. Existing databases are
never deleted automatically.

For an existing pre-Alembic CDR database, `init_db.py` safely stamps the known
baseline only when all expected legacy tables exist, then applies subsequent
integrity migrations. If a migration detects real duplicate rows, it fails
without deleting or merging them; resolve the data explicitly and rerun.
