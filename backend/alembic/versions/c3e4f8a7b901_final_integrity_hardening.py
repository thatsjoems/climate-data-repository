"""Final integrity hardening: current-version uniqueness, exact interest rates and structured audit metadata.

This migration is additive and refuses to silently delete or merge business data.
It deterministically repairs duplicate current flags before installing the
database-level one-current-version invariant.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text

revision = "c3e4f8a7b901"
down_revision = "b7f2c91d4e60"
branch_labels = None
depends_on = None


def _has_column(bind, table, column):
    return column in {c["name"] for c in inspect(bind).get_columns(table)}


def _has_index(bind, table, name):
    return name in {i["name"] for i in inspect(bind).get_indexes(table)}


def upgrade():
    bind = op.get_bind()
    insp = inspect(bind)
    tables = set(insp.get_table_names())

    if "submissions" in tables:
        # Repair legacy rows deterministically before adding the partial unique index.
        # Prefer the newest APPROVED version; if none exists, prefer newest VALID.
        groups = bind.execute(text("""
            SELECT institution_id, reporting_period
            FROM submissions
            WHERE is_current = TRUE
            GROUP BY institution_id, reporting_period
            HAVING COUNT(*) > 1
        """)).all()
        for institution_id, reporting_period in groups:
            candidates = bind.execute(text("""
                SELECT id, status, created_at, version_number
                FROM submissions
                WHERE institution_id = :institution_id
                  AND reporting_period = :period
                  AND is_current = TRUE
                ORDER BY
                  CASE WHEN status = 'APPROVED' THEN 0
                       WHEN status = 'VALID' THEN 1
                       ELSE 2 END,
                  created_at DESC,
                  version_number DESC,
                  id DESC
            """), {"institution_id": institution_id, "period": reporting_period}).mappings().all()
            if not candidates:
                continue
            chosen = candidates[0]["id"]
            bind.execute(text("""
                UPDATE submissions
                SET is_current = FALSE
                WHERE institution_id = :institution_id
                  AND reporting_period = :period
            """), {"institution_id": institution_id, "period": reporting_period})
            bind.execute(text("""
                UPDATE submissions
                SET is_current = TRUE
                WHERE id = :id
            """), {"id": chosen})

        if not _has_index(bind, "submissions", "uq_submissions_one_current_per_institution_period"):
            if bind.dialect.name == "postgresql":
                op.create_index(
                    "uq_submissions_one_current_per_institution_period",
                    "submissions",
                    ["institution_id", "reporting_period"],
                    unique=True,
                    postgresql_where=sa.text("is_current = true"),
                )
            else:
                op.create_index(
                    "uq_submissions_one_current_per_institution_period",
                    "submissions",
                    ["institution_id", "reporting_period"],
                    unique=True,
                    sqlite_where=sa.text("is_current = 1"),
                )

    if "submission_records" in tables:
        # Interest rates are percentages, not monetary floats. Numeric makes
        # calculations deterministic and avoids binary floating-point artifacts.
        cols = {c["name"]: c for c in inspect(bind).get_columns("submission_records")}
        if "annual_interest_rate" in cols:
            if bind.dialect.name == "sqlite":
                with op.batch_alter_table("submission_records", recreate="always") as batch:
                    batch.alter_column(
                        "annual_interest_rate",
                        existing_type=cols["annual_interest_rate"]["type"],
                        type_=sa.Numeric(8, 4),
                        existing_nullable=True,
                    )
            else:
                op.alter_column(
                    "submission_records",
                    "annual_interest_rate",
                    existing_type=cols["annual_interest_rate"]["type"],
                    type_=sa.Numeric(8, 4),
                    existing_nullable=True,
                )

    if "climate_records" in tables:
        # SQLite batch table recreation in the previous migration can drop
        # expression-based unique indexes. Recreate them here and refuse to
        # guess if pre-existing duplicates make that unsafe.
        duplicate_queries = [
            """SELECT 1 FROM climate_records WHERE source_record_id IS NOT NULL
               GROUP BY region, COALESCE(district, ''), year, COALESCE(month, 0),
                        source_record_id, COALESCE(station_id, '')
               HAVING COUNT(*) > 1 LIMIT 1""",
            """SELECT 1 FROM climate_records WHERE source_record_id IS NULL
               AND station_id IS NOT NULL
               GROUP BY region, COALESCE(district, ''), year, COALESCE(month, 0),
                        station_id
               HAVING COUNT(*) > 1 LIMIT 1""",
        ]
        for sql in duplicate_queries:
            if bind.execute(text(sql)).first() is not None:
                raise RuntimeError(
                    "Existing duplicate climate observations prevent final integrity hardening. "
                    "Resolve duplicates explicitly; no rows are deleted automatically."
                )
        if bind.dialect.name in {"postgresql", "sqlite"}:
            if not _has_index(bind, "climate_records", "uq_climate_observation_source_identity"):
                op.execute(
                    "CREATE UNIQUE INDEX uq_climate_observation_source_identity "
                    "ON climate_records (region, COALESCE(district, ''), year, "
                    "COALESCE(month, 0), source_record_id, COALESCE(station_id, '')) "
                    "WHERE source_record_id IS NOT NULL"
                )
            if not _has_index(bind, "climate_records", "uq_climate_observation_station_identity"):
                op.execute(
                    "CREATE UNIQUE INDEX uq_climate_observation_station_identity "
                    "ON climate_records (region, COALESCE(district, ''), year, "
                    "COALESCE(month, 0), station_id) "
                    "WHERE source_record_id IS NULL AND station_id IS NOT NULL"
                )

    if "audit_logs" in tables and not _has_column(bind, "audit_logs", "details_json"):
        op.add_column("audit_logs", sa.Column("details_json", sa.JSON(), nullable=True))

    # Climate geography is already validated against the canonical Tanzania
    # reference dataset in the ingestion service. We deliberately do not add
    # hard FKs to free-text region/district columns here because doing so would
    # make legacy historical rows with old spelling/casing un-migratable.
    # New ingestion continues to reject invalid region/district relationships.


def downgrade():
    bind = op.get_bind()
    insp = inspect(bind)
    tables = set(insp.get_table_names())

    if "audit_logs" in tables and _has_column(bind, "audit_logs", "details_json"):
        op.drop_column("audit_logs", "details_json")

    if "submission_records" in tables:
        cols = {c["name"]: c for c in inspect(bind).get_columns("submission_records")}
        if "annual_interest_rate" in cols:
            if bind.dialect.name == "sqlite":
                with op.batch_alter_table("submission_records", recreate="always") as batch:
                    batch.alter_column(
                        "annual_interest_rate",
                        existing_type=cols["annual_interest_rate"]["type"],
                        type_=sa.Float(),
                        existing_nullable=True,
                    )
            else:
                op.alter_column(
                    "submission_records",
                    "annual_interest_rate",
                    existing_type=cols["annual_interest_rate"]["type"],
                    type_=sa.Float(),
                    existing_nullable=True,
                )

    if "submissions" in tables and _has_index(bind, "submissions", "uq_submissions_one_current_per_institution_period"):
        op.drop_index("uq_submissions_one_current_per_institution_period", table_name="submissions")
