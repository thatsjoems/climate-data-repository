"""two-step sign-in: columns on users and one CHECK constraint
Revision ID: f3a7c1e5b829
Revises: e9b3c7a1d5f2

Adds users.mfa_enabled (default false), mfa_secret_encrypted, mfa_recovery_hashes, mfa_last_step and mfa_enrolled_at, and
ck_users_mfa_enabled_has_secret (a user marked as enrolled must have a secret). Every existing user starts as not enrolled, so
nothing changes for anyone until MFA_REQUIRED is switched on or a person enrols. Deletes and rewrites nothing; idempotent.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "f3a7c1e5b829"
down_revision = "e9b3c7a1d5f2"
branch_labels = None
depends_on = None

COLUMNS = [
    ("mfa_enabled", "BOOLEAN NOT NULL DEFAULT FALSE", sa.Column("mfa_enabled", sa.Boolean(), nullable=False, server_default=sa.false())),
    ("mfa_secret_encrypted", "TEXT", sa.Column("mfa_secret_encrypted", sa.Text(), nullable=True)),
    ("mfa_recovery_hashes", "TEXT", sa.Column("mfa_recovery_hashes", sa.Text(), nullable=True)),
    ("mfa_last_step", "INTEGER", sa.Column("mfa_last_step", sa.Integer(), nullable=True)),
    ("mfa_enrolled_at", "TIMESTAMP", sa.Column("mfa_enrolled_at", sa.DateTime(), nullable=True)),
]
CHECK = ("users", "ck_users_mfa_enabled_has_secret", "NOT mfa_enabled OR mfa_secret_encrypted IS NOT NULL")


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "users" not in inspector.get_table_names():
        return
    present = {c["name"] for c in inspector.get_columns("users")}
    for name, ddl, column in COLUMNS:
        if name in present:
            continue
        if bind.dialect.name == "postgresql":
            op.execute(f"ALTER TABLE users ADD COLUMN {name} {ddl}")
        else:
            with op.batch_alter_table("users") as batch_op:
                batch_op.add_column(column)
    table, name, condition = CHECK
    if name not in {c["name"] for c in inspect(bind).get_check_constraints(table)}:
        if bind.dialect.name == "postgresql":
            op.execute(f"ALTER TABLE {table} ADD CONSTRAINT {name} CHECK ({condition})")
        else:
            with op.batch_alter_table(table) as batch_op:
                batch_op.create_check_constraint(name, condition)


def downgrade() -> None:
    bind = op.get_bind()
    if "users" not in inspect(bind).get_table_names():
        return
    if bind.dialect.name == "postgresql":
        op.execute(f"ALTER TABLE users DROP CONSTRAINT IF EXISTS {CHECK[1]}")
        for name, _, _ in COLUMNS:
            op.execute(f"ALTER TABLE users DROP COLUMN IF EXISTS {name}")
    else:
        with op.batch_alter_table("users") as batch_op:
            try:
                batch_op.drop_constraint(CHECK[1], type_="check")
            except Exception:
                pass
            for name, _, _ in COLUMNS:
                batch_op.drop_column(name)
