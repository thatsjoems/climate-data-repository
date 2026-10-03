"""Harden submission versioning, financial types, climate periods and JSON snapshots.

This migration is additive/backward-compatible where possible. It does not delete
or merge business rows. Existing submission history is assigned deterministic
version numbers in creation order and the newest VALID/APPROVED row per
institution/period becomes the current analytical version.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text

revision = "b7f2c91d4e60"
down_revision = "9c1852419557"
branch_labels = None
depends_on = None


def _has_column(bind, table, column):
    return column in {c["name"] for c in inspect(bind).get_columns(table)}


def _has_index(bind, table, name):
    return name in {i["name"] for i in inspect(bind).get_indexes(table)}


def _add_column_if_missing(table, column):
    bind = op.get_bind()
    if not _has_column(bind, table, column.name):
        op.add_column(table, column)


def upgrade():
    bind = op.get_bind()
    insp = inspect(bind)
    tables = set(insp.get_table_names())

    if "submissions" in tables:
        _add_column_if_missing("submissions", sa.Column("version_number", sa.Integer(), nullable=True))
        _add_column_if_missing("submissions", sa.Column("previous_submission_id", sa.String(), nullable=True))
        _add_column_if_missing("submissions", sa.Column("is_current", sa.Boolean(), nullable=True))

        rows = bind.execute(text("""
            SELECT id, institution_id, reporting_period, status, created_at
            FROM submissions
            ORDER BY institution_id, reporting_period, created_at, id
        """)).mappings().all()
        counters = {}
        for row in rows:
            key = (row["institution_id"], row["reporting_period"])
            counters[key] = counters.get(key, 0) + 1
            bind.execute(text("""
                UPDATE submissions
                SET version_number = :v
                WHERE id = :id
            """), {"v": counters[key], "id": row["id"]})

        # Build the lineage in creation order.
        previous = {}
        for row in rows:
            key = (row["institution_id"], row["reporting_period"])
            bind.execute(text("""
                UPDATE submissions
                SET previous_submission_id = :prev
                WHERE id = :id
            """), {"prev": previous.get(key), "id": row["id"]})
            previous[key] = row["id"]

        # Only a valid/approved version can be the analytical current version.
        # Prefer the newest APPROVED; if none exists, prefer newest VALID.
        groups = bind.execute(text("""
            SELECT institution_id, reporting_period,
                   MAX(CASE WHEN status = 'APPROVED' THEN created_at END) AS approved_at,
                   MAX(CASE WHEN status = 'VALID' THEN created_at END) AS valid_at
            FROM submissions
            GROUP BY institution_id, reporting_period
        """)).mappings().all()
        for group in groups:
            chosen = None
            if group["approved_at"] is not None:
                chosen = bind.execute(text("""
                    SELECT id FROM submissions
                    WHERE institution_id=:institution_id AND reporting_period=:period
                      AND status='APPROVED' AND created_at=:created_at
                    ORDER BY version_number DESC LIMIT 1
                """), {"institution_id": group["institution_id"], "period": group["reporting_period"], "created_at": group["approved_at"]}).scalar()
            elif group["valid_at"] is not None:
                chosen = bind.execute(text("""
                    SELECT id FROM submissions
                    WHERE institution_id=:institution_id AND reporting_period=:period
                      AND status='VALID' AND created_at=:created_at
                    ORDER BY version_number DESC LIMIT 1
                """), {"institution_id": group["institution_id"], "period": group["reporting_period"], "created_at": group["valid_at"]}).scalar()
            bind.execute(text("""
                UPDATE submissions SET is_current = CASE WHEN id=:chosen THEN TRUE ELSE FALSE END
                WHERE institution_id=:institution_id AND reporting_period=:period
            """), {"chosen": chosen or "__none__", "institution_id": group["institution_id"], "period": group["reporting_period"]})

        bind.execute(text("UPDATE submissions SET version_number = 1 WHERE version_number IS NULL"))
        bind.execute(text("UPDATE submissions SET is_current = FALSE WHERE is_current IS NULL"))
        if bind.dialect.name != "sqlite":
            op.alter_column("submissions", "version_number", nullable=False, server_default="1")
            op.alter_column("submissions", "is_current", nullable=False, server_default=sa.false())

        if not _has_index(bind, "submissions", "ix_submissions_version_lookup"):
            op.create_index("ix_submissions_version_lookup", "submissions", ["institution_id", "reporting_period", "version_number"], unique=False)
        if not _has_index(bind, "submissions", "ix_submissions_previous_submission"):
            op.create_index("ix_submissions_previous_submission", "submissions", ["previous_submission_id"], unique=False)
        # Add self-FK only after all existing values have been populated.
        existing_fks = {tuple(f["constrained_columns"]): f for f in insp.get_foreign_keys("submissions")}
        if ("previous_submission_id",) not in existing_fks:
            if bind.dialect.name == "sqlite":
                with op.batch_alter_table("submissions", recreate="always") as batch:
                    batch.create_foreign_key("fk_submissions_previous_submission", "submissions", ["previous_submission_id"], ["id"])
            else:
                op.create_foreign_key("fk_submissions_previous_submission", "submissions", "submissions", ["previous_submission_id"], ["id"])

    if "submission_records" in tables:
        _add_column_if_missing("submission_records", sa.Column("disbursement_date_value", sa.Date(), nullable=True))
        _add_column_if_missing("submission_records", sa.Column("maturity_date_value", sa.Date(), nullable=True))
        _add_column_if_missing("submission_records", sa.Column("collateral_pledged_date_value", sa.Date(), nullable=True))
        # Parse only unambiguous ISO-like source strings into the canonical date
        # columns. Ambiguous legacy text is intentionally left NULL rather than
        # guessed; the original raw value remains available for audit/review.
        # GLOB is SQLite-only syntax - PostgreSQL has no GLOB function at all
        # (this raised a plain syntax error there, not a behavioural
        # difference); PostgreSQL's equivalent is the POSIX regex match
        # operator `~`, with an explicit `::date` cast for the conversion
        # itself rather than SQLite's `date(...)` function.
        if bind.dialect.name == "postgresql":
            bind.execute(text("""
                UPDATE submission_records
                SET disbursement_date_value = CASE
                    WHEN disbursement_date ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' THEN disbursement_date::date
                    ELSE disbursement_date_value END,
                    maturity_date_value = CASE
                    WHEN maturity_date ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' THEN maturity_date::date
                    ELSE maturity_date_value END,
                    collateral_pledged_date_value = CASE
                    WHEN collateral_pledged_date ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' THEN collateral_pledged_date::date
                    ELSE collateral_pledged_date_value END
            """))
        elif bind.dialect.name == "sqlite":
            bind.execute(text("""
                UPDATE submission_records
                SET disbursement_date_value = CASE
                    WHEN disbursement_date GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]' THEN date(disbursement_date)
                    ELSE disbursement_date_value END,
                    maturity_date_value = CASE
                    WHEN maturity_date GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]' THEN date(maturity_date)
                    ELSE maturity_date_value END,
                    collateral_pledged_date_value = CASE
                    WHEN collateral_pledged_date GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]' THEN date(collateral_pledged_date)
                    ELSE collateral_pledged_date_value END
            """))

    if "submission_records" in tables:
        # Reject ambiguous pre-existing duplicates rather than silently deleting them.
        duplicate = bind.execute(text("""
            SELECT 1 FROM submission_records
            WHERE loan_id IS NOT NULL
            GROUP BY submission_id, loan_id
            HAVING COUNT(*) > 1
            LIMIT 1
        """)).first()
        if duplicate:
            raise RuntimeError("Duplicate loan_id values already exist within a submission. Resolve them explicitly before applying b7f2c91d4e60.")
        if not _has_index(bind, "submission_records", "uq_submission_records_submission_loan"):
            if bind.dialect.name == "postgresql":
                op.execute("CREATE UNIQUE INDEX uq_submission_records_submission_loan ON submission_records (submission_id, loan_id) WHERE loan_id IS NOT NULL")
            else:
                op.create_index("uq_submission_records_submission_loan", "submission_records", ["submission_id", "loan_id"], unique=True)

        for idx_name, col_name in [
            ("ix_submission_records_disbursement_date_value", "disbursement_date_value"),
            ("ix_submission_records_maturity_date_value", "maturity_date_value"),
            ("ix_submission_records_collateral_pledged_date_value", "collateral_pledged_date_value"),
        ]:
            if not _has_index(bind, "submission_records", idx_name):
                op.create_index(idx_name, "submission_records", [col_name], unique=False)

        # Monetary columns are exact NUMERIC values, not binary floating point.
        numeric_cols = [
            "annual_turnover_tzs", "loan_amount_tzs", "outstanding_principal_tzs",
            "collateral_value_tzs", "collateral_forced_sale_value_tzs", "insurance_value_protected_tzs",
        ]
        if bind.dialect.name == "sqlite":
            with op.batch_alter_table("submission_records", recreate="always") as batch:
                for col in numeric_cols:
                    batch.alter_column(col, existing_type=sa.Float(), type_=sa.Numeric(20, 2), existing_nullable=True)
        else:
            for col in numeric_cols:
                op.alter_column("submission_records", col, existing_type=sa.Float(), type_=sa.Numeric(20, 2), existing_nullable=True)

    if "climate_records" in tables:
        # Climate reporting period must use the same canonical YYYY-Qn representation.
        existing_checks = {c["name"] for c in insp.get_check_constraints("climate_records")}
        if "ck_climate_records_reporting_period_format" not in existing_checks:
            condition = "reporting_period IS NULL OR (length(reporting_period) = 7 AND substr(reporting_period, 5, 2) = '-Q' AND substr(reporting_period, 7, 1) IN ('1','2','3','4'))"
            if bind.dialect.name == "sqlite":
                with op.batch_alter_table("climate_records", recreate="always") as batch:
                    batch.create_check_constraint("ck_climate_records_reporting_period_format", condition)
            else:
                op.create_check_constraint("ck_climate_records_reporting_period_format", "climate_records", condition)

    if "risk_advisory_notes" in tables and bind.dialect.name == "postgresql":
        # Existing snapshots are JSON strings created by the application. Fail loudly
        # rather than silently corrupt a non-JSON snapshot.
        bad = bind.execute(text("""
            SELECT id FROM risk_advisory_notes
            WHERE data_snapshot IS NOT NULL
              AND data_snapshot::json IS NULL
            LIMIT 1
        """)).first()
        if bad:
            raise RuntimeError("A risk advisory contains a non-JSON data_snapshot; clean that row before migrating to JSON.")
        op.execute("ALTER TABLE risk_advisory_notes ALTER COLUMN data_snapshot TYPE JSON USING data_snapshot::json")


def downgrade():
    bind = op.get_bind()
    insp = inspect(bind)
    tables = set(insp.get_table_names())
    if "risk_advisory_notes" in tables and bind.dialect.name == "postgresql":
        op.execute("ALTER TABLE risk_advisory_notes ALTER COLUMN data_snapshot TYPE TEXT USING data_snapshot::text")
    if "submission_records" in tables:
        for col in [
            "annual_turnover_tzs", "loan_amount_tzs", "outstanding_principal_tzs",
            "collateral_value_tzs", "collateral_forced_sale_value_tzs", "insurance_value_protected_tzs",
        ]:
            op.alter_column("submission_records", col, existing_type=sa.Numeric(20, 2), type_=sa.Float(), existing_nullable=True)
        try:
            op.drop_index("uq_submission_records_submission_loan", table_name="submission_records")
        except Exception:
            pass
    if "submissions" in tables:
        try:
            op.drop_constraint("fk_submissions_previous_submission", "submissions", type_="foreignkey")
        except Exception:
            pass
        for name in ["ix_submissions_previous_submission", "ix_submissions_version_lookup"]:
            try:
                op.drop_index(name, table_name="submissions")
            except Exception:
                pass
        for col in ["previous_submission_id", "version_number", "is_current"]:
            try:
                op.drop_column("submissions", col)
            except Exception:
                pass
