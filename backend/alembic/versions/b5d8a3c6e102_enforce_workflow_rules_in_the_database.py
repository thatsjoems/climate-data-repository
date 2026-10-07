"""enforce three workflow rules in the database that only the application enforced
Revision ID: b5d8a3c6e102
Revises: f4a9c2d71b05

Why this migration exists. Three rules held only because the application code kept them; a second
client, a script or a manual edit could have broken them without the database objecting:

    ck_submissions_current_only_valid_or_approved   only a VALID or APPROVED submission can be current
    ck_submissions_reviewer_not_submitter           the reviewer is never the person who uploaded it (BR-03)
    ck_users_institution_user_has_institution       an institution user belongs to an institution (BR-15)

The last rule is deliberately ONE-WAY. The reverse (staff roles must have no institution) is not
enforced because the demonstration seed attaches the administrator and the BOT analyst to the BOT
institution record, and an existing database holds those rows: a reverse rule would stop them signing in.

Safe on a database that already holds data (same approach as f4a9c2d71b05). On PostgreSQL each
constraint is added NOT VALID (enforced for every new or updated row) and VALIDATEd immediately if no
existing row breaks it; if some do, the number is logged and the constraint is left NOT VALID.
Nothing is ever deleted or rewritten here. SQLite cannot add an unvalidated CHECK, so there (a legacy
or development database only) existing violations stop the migration.
Idempotent: a constraint that already exists (by name) is skipped.
"""
import logging
from alembic import op
from sqlalchemy import inspect, text

revision = "b5d8a3c6e102"
down_revision = "f4a9c2d71b05"
branch_labels = None
depends_on = None
log = logging.getLogger("alembic.runtime.migration")

# (table, constraint name, condition exactly as in models.py, SQL selecting the rows that break it)
CONSTRAINTS = [
    (
        "submissions",
        "ck_submissions_current_only_valid_or_approved",
        "NOT is_current OR status IN ('VALID', 'APPROVED')",
        "is_current AND status NOT IN ('VALID', 'APPROVED')",
    ),
    (
        "submissions",
        "ck_submissions_reviewer_not_submitter",
        "reviewed_by_user_id IS NULL OR submitted_by_user_id IS NULL OR reviewed_by_user_id <> submitted_by_user_id",
        "reviewed_by_user_id IS NOT NULL AND submitted_by_user_id IS NOT NULL AND reviewed_by_user_id = submitted_by_user_id",
    ),
    (
        "users",
        "ck_users_institution_user_has_institution",
        "role <> 'INSTITUTION_USER' OR institution_id IS NOT NULL",
        "role = 'INSTITUTION_USER' AND institution_id IS NULL",
    ),
]


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    for table, name, condition, violation in CONSTRAINTS:
        if table not in tables:
            continue
        if name in {c["name"] for c in inspector.get_check_constraints(table)}:
            continue

        violators = bind.execute(text(f"SELECT COUNT(*) FROM {table} WHERE {violation}")).scalar() or 0

        if bind.dialect.name == "postgresql":
            op.execute(f"ALTER TABLE {table} ADD CONSTRAINT {name} CHECK ({condition}) NOT VALID")
            if violators == 0:
                op.execute(f"ALTER TABLE {table} VALIDATE CONSTRAINT {name}")
            else:
                log.warning(
                    "%s: %d existing row(s) in %s break this rule. The constraint is enforced for new and "
                    "updated rows but left NOT VALID. Find them with: SELECT * FROM %s WHERE %s; then fix "
                    "them and run: ALTER TABLE %s VALIDATE CONSTRAINT %s;",
                    name, violators, table, table, violation, table, name,
                )
        else:
            if violators:
                raise RuntimeError(
                    f"{violators} existing row(s) in {table} break {name} ({condition}). This database "
                    f"engine cannot add an unvalidated CHECK constraint; correct those rows explicitly "
                    f"and re-run - no rows are changed or deleted automatically."
                )
            with op.batch_alter_table(table) as batch_op:
                batch_op.create_check_constraint(name, condition)


def downgrade() -> None:
    bind = op.get_bind()
    tables = set(inspect(bind).get_table_names())
    for table, name, _condition, _violation in CONSTRAINTS:
        if table not in tables:
            continue
        if bind.dialect.name == "postgresql":
            op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {name}")
        else:
            with op.batch_alter_table(table) as batch_op:
                try:
                    batch_op.drop_constraint(name, type_="check")
                except Exception:
                    pass
