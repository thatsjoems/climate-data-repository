# Database Schema

This system uses SQLAlchemy ORM (see `backend/app/models/models.py`) as the
single source of truth for the database structure.

Tables are created automatically when you run:

```
python init_db.py
```

This works for both SQLite (default, no setup required) and PostgreSQL (after
changing DATABASE_URL in `.env`).

## Entity Summary

| Table | Purpose |
|---|---|
| institutions | Reporting institutions (banks, TMA, etc.) |
| users | All system users (Admin, BOT_USER, INSTITUTION_USER) |
| submissions | Each data file submission |
| submission_records | Each row of data within a submission (e.g. one loan) |
| validation_errors | Errors found while validating a submission |
| climate_records | Climate data (SAMPLE/SYNTHETIC - see backend README) |
| audit_logs | Records of significant system events |

For a full ERD, use a tool such as `dbdiagram.io` from the structure above, or
`sqlalchemy_schemadisplay` once all packages are installed.
